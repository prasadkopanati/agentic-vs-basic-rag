"""Agentic RAG pipeline: iterative rewriter → retriever → grader → router loop.

Graph topology (from docs/background.md):
    rewriter → retriever → grader → (router) → generator → END
                              ↑                      |
                              └─── retry_counter ────┘ (when not relevant)
"""

from __future__ import annotations

import json
import operator
import os
import time
from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

import config
from pipelines.basic_rag import _build_chunks, _build_context_str, _get_vectorstore

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    original_query: str
    rewritten_query: str
    retrieved_chunks: list[dict]
    grader_relevant: bool
    grader_feedback: str             # gap description from grader; empty when relevant
    grader_score: float              # raw score from the latest grader call (0.0–1.0)
    best_grader_score: float         # running max of grader_score across all retries
    prev_grader_score: float         # best score carried from previous rewriter call; stagnation detection
    consecutive_stable_retries: int  # retries where best_grader_score did not improve
    last_retrieval_novel_count: int  # new chunks added by the most recent retrieval
    retry_count: int
    answer: str
    # Annotated with operator.add → LangGraph accumulates these automatically
    step_log: Annotated[list[dict], operator.add]
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class AgenticRAGResult:
    query: str
    answer: str
    chunks: list[dict]
    step_log: list[dict]
    retry_count: int
    retrieval_confidence: float
    latency_s: float
    input_tokens: int
    output_tokens: int
    grader_scores: list[float] = field(default_factory=list)  # raw score per grader call
    best_grader_score: float = 0.0                            # peak coverage reached


# ---------------------------------------------------------------------------
# Pure-logic helpers (exported for unit testing)
# ---------------------------------------------------------------------------


def _compute_retrieval_confidence(
    retry_count: int, max_retries: int = config.MAX_RETRIES
) -> float:
    """Retry-derived confidence: 1.0 at 0 retries, 0.0 at max_retries."""
    if max_retries == 0:
        return 1.0
    return max(0.0, 1.0 - retry_count / max_retries)


def _parse_grader_response(text: str) -> tuple[bool, str, float]:
    """Return (is_relevant, gap_description, grading_score).

    Primary path: parse JSON produced by the updated grader prompt.
    Fallback: legacy YES/NO text format for model non-compliance.
    """
    stripped = text.strip()

    # --- Primary path: JSON ---
    # Scan for the outermost {...} block; the model may add a preamble despite
    # instructions, so we don't require the response to start with '{'.
    json_start = stripped.find("{")
    json_end = stripped.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        try:
            data = json.loads(stripped[json_start:json_end])
            result = str(data.get("grading_result", "no")).lower() == "yes"
            feedback = str(data.get("feedback", "")).strip()
            raw_score = data.get("grading_score", 1.0 if result else 0.0)
            score = max(0.0, min(1.0, float(raw_score)))
            return result, feedback, score
        except (json.JSONDecodeError, ValueError, TypeError):
            pass  # fall through to legacy parser

    # --- Fallback: legacy YES / "NO. Missing: ..." text format ---
    lower = stripped.lower()

    # YES — model may reason first then revise
    if not lower.startswith("no"):
        for marker in ("revised assessment: yes", "final assessment: yes",
                       "final answer: yes", "overall assessment: yes"):
            if marker in lower:
                return True, "", 1.0
        for line in stripped.splitlines():
            if line.strip().upper() == "YES":
                return True, "", 1.0
    if stripped.upper().startswith("YES"):
        return True, "", 1.0

    # NO — extract gap description
    feedback = ""
    if "missing:" in lower:
        feedback = stripped[lower.index("missing:") + len("missing:"):].strip()
        for sep in (".\n", "\n\n"):
            if sep in feedback:
                feedback = feedback[:feedback.index(sep) + 1].strip()
                break
    elif stripped.upper().startswith("NO"):
        feedback = stripped[2:].lstrip(" .—-:")

    # score=0.0 in fallback: unknown, conservative signal for stagnation check
    return False, feedback, 0.0


def _route(state: AgentState) -> str:
    """Route to generator (relevant, budget exhausted, or score plateau) or retry_counter."""
    if state["grader_relevant"]:
        return "generator"
    if state["retry_count"] >= config.MAX_RETRIES:
        return "generator"
    # Plateau exit: best score hasn't improved for 2+ consecutive retries and we have
    # meaningful coverage — the corpus ceiling has been reached; further retries waste budget.
    if (state.get("consecutive_stable_retries", 0) >= 2
            and state.get("best_grader_score", 0.0) >= 0.50):
        return "generator"
    return "retry_counter"


# ---------------------------------------------------------------------------
# LLM factories — separate instances so generator can use a higher token budget
# ---------------------------------------------------------------------------

_llm: ChatAnthropic | None = None
_generator_llm: ChatAnthropic | None = None
_kb_manifest: dict | None = None

_KB_MANIFEST_PATH = "./artifacts/kb_manifest.json"


def _get_kb_manifest() -> dict:
    """Load the pre-computed per-document vocabulary manifest (singleton)."""
    global _kb_manifest
    if _kb_manifest is None:
        try:
            with open(_kb_manifest_path(), encoding="utf-8") as f:
                _kb_manifest = json.load(f)
        except FileNotFoundError:
            _kb_manifest = {}
    return _kb_manifest


def _kb_manifest_path() -> str:
    return _KB_MANIFEST_PATH


def _get_manifest_vocabulary(
    feedback: str, max_chars: int = 300, manifest: dict | None = None
) -> str:
    """Return corpus-native vocabulary relevant to the identified gap.

    Scores manifest documents by keyword overlap with the grader feedback using
    topics, thresholds, and citations (not key_terms, which are often procedural
    sentences that inflate scores for FAQ-style documents without containing
    retrieval-useful vocabulary).

    Returns only thresholds and citations — hard facts and regulatory references
    that the rewriter can embed directly in a retrieval query. Procedural key_terms
    are excluded from output because they don't improve embedding similarity.

    manifest: optional override for testing; defaults to the loaded kb_manifest.json.
    """
    if manifest is None:
        manifest = _get_kb_manifest()
    if not manifest:
        return ""

    feedback_lower = feedback.lower()
    scored: list[tuple[int, dict]] = []

    for entry in manifest.values():
        # Use topics + short key_terms (< 30 chars) as scoring signals.
        # Long key_terms are procedural sentences — they inflate scores for FAQ-style
        # docs that mention a topic repeatedly without containing retrieval vocabulary.
        short_key_terms = [t for t in entry.get("key_terms", []) if len(t) < 30]
        score_terms = entry.get("topics", []) + short_key_terms
        hits = sum(1 for term in score_terms if term.lower() in feedback_lower)
        if hits > 0:
            # Secondary sort key: docs with more thresholds + citations are more fact-dense
            # and produce better retrieval vocabulary than FAQ/procedural docs.
            fact_density = len(entry.get("thresholds", [])) + len(entry.get("citations", []))
            scored.append((hits, fact_density, entry))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    vocab: list[str] = []
    seen: set[str] = set()
    for _, _density, entry in scored[:3]:
        for item in (entry.get("thresholds", []) + entry.get("citations", [])):
            if item not in seen:
                vocab.append(item)
                seen.add(item)

    result = ", ".join(vocab)
    return result[:max_chars] if len(result) > max_chars else result


def _get_llm() -> ChatAnthropic:
    """Shared LLM for rewriter and grader (short outputs, 512 tokens sufficient)."""
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(
            model=config.LLM_MODEL,
            api_key=os.environ["ANTHROPIC_API_KEY"],
            temperature=0,
            max_tokens=512,
        )
    return _llm


def _get_generator_llm() -> ChatAnthropic:
    """Dedicated LLM for generator — higher token budget for multi-source answers."""
    global _generator_llm
    if _generator_llm is None:
        _generator_llm = ChatAnthropic(
            model=config.LLM_MODEL,
            api_key=os.environ["ANTHROPIC_API_KEY"],
            temperature=0,
            max_tokens=1024,
        )
    return _generator_llm


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# First attempt: convert the user question into a short, focused retrieval query.
# Vector embeddings degrade with query length — 10-20 words retrieves better
# than a 60-word multi-clause question. No acronym injection yet; let natural
# vocabulary surface the most likely document cluster first.
_REWRITER_PROMPT_INITIAL = """\
Convert the following compliance scenario into a concise retrieval query for an NCUA \
regulatory knowledge base. The query must be 10–20 words. Capture the 2–3 most \
important concepts. Do not add regulatory acronyms or agency names not already \
present in the original question. Output only the query, no preamble.

Question: {query}

Retrieval query:"""

# Retry when the previous retrieval found new chunks but the grader identified a
# specific missing dimension. The key challenge: grader feedback is written in the
# asker's vocabulary ("formal written action", "closing exam without requirements")
# but the source documents use regulatory-answer vocabulary ("Document of Resolution",
# "DOR not required", "plan of action"). The rewriter must translate across this gap.
_REWRITER_PROMPT_RETRY = """\
The previous retrieval missed this regulatory dimension:
{grader_feedback}

{coverage_note}

{corpus_vocabulary_section}\
Write a short retrieval query (10–20 words) that targets ONLY this missing aspect.

CRITICAL — vocabulary translation: the gap above is described in the ASKER'S language, \
but your query must use DOCUMENT language — the exact regulatory terms, defined phrases, \
and citations that appear in an NCUA source document that ANSWERS this dimension. \
Apply these translation rules as a fallback when no corpus vocabulary is listed above:
- "formal written supervisory action / commitment / corrective document" \
  → Document of Resolution, DOR, written plan of action, corrective action required
- "what happens after exam / examiner next step / no requirements imposed" \
  → DOR not required, plan of action not necessary, examiner discretion, \
  12 CFR 741.3 credit union plan of action
- "federal reporting / data collection obligation outside NCUA exam" \
  → HMDA, Regulation C, Home Mortgage Disclosure Act, data collection submission CFPB
- "collateral valuation / property documentation for commercial loan" \
  → Title XI, certified appraiser, state-licensed appraiser, 12 CFR Part 722, \
  appraisal threshold commercial real estate
- "mandatory lending restriction / loan origination pause when undercapitalized" \
  → 12 CFR 702.107, member business lending restriction, total asset growth cap, \
  undercapitalized mandatory supervisory action
- "threshold / classification boundary in a supervisory test" \
  → use the exact numeric value and regulatory term from the table \
  (e.g., "post-shock NEV ratio below 4 percent High classification supervisory test")
- "SAR dollar threshold / SAR minimum amount / suspicious activity reporting trigger amount / \
  SAR filing amount / minimum dollar amount for SAR filing / \
  dollar threshold when suspect can be identified / SAR filing amount when suspect identified" \
  → "credit union SAR criminal violations aggregating 5000 suspect identified \
  748.1(d)(1) reportable activity BSA filing requirement"

Stay within NCUA credit union regulatory vocabulary. Do not import terms from other \
banking frameworks (e.g., do not use OCC, CCAR, Basel, or FFIEC terminology unless \
that agency is explicitly referenced in the original question).

Do not reuse vocabulary from the previous query.

Previous query (do not repeat): {previous_rewrite}

Retrieval query:"""

# Dead-end retry: previous retrieval returned zero new chunks, meaning the current
# vocabulary is exhausted. Abandon it entirely and approach from a different angle.
_REWRITER_PROMPT_DEAD_END = """\
The previous retrieval query found no new documents — that search vector is exhausted.

Original question: {query}
Exhausted query: {previous_rewrite}
Known gap: {grader_feedback}

Write a short retrieval query (10–20 words) using COMPLETELY DIFFERENT keywords than \
the exhausted query. Think about synonyms, adjacent regulatory concepts, or the \
regulator's perspective rather than the institution's. \
Output only the query, no preamble.

Retrieval query:"""

# Grader evaluates completeness across ALL regulatory dimensions implied by
# the original question, not just topical relevance.
# Static instructions cached in the system message; question + context sent as
# human message so the cache prefix is stable across all retry calls for a query.
_GRADER_SYSTEM = """\
You are a strict completeness grader for a banking compliance knowledge base.

Evaluate whether retrieved documents COMPREHENSIVELY address every regulatory \
dimension of the question.

Grade as YES only if ALL of the following hold:
- Every distinct obligation, threshold, or risk category EXPLICITLY asked for \
  in the question is substantively addressed (focus on what the question asks, \
  not additional sub-questions you generate)
- Specific regulatory guidance is provided for the actual scenario described \
  (not just general background on the topic)
- Any member-specific characteristics in the question (e.g. foreign official \
  status, transaction patterns, account type) correspond to regulatory \
  requirements that the documents explicitly cover

Grade as NO if a SIGNIFICANT dimension of what the question asks is missing or \
only superficially addressed. Do NOT reject based on:
- Clarifying commentary not present (e.g., "whether these are percentage points \
  or absolute values") when the numerical thresholds themselves are stated
- Additional metrics or table dimensions the question does not ask about — if \
  the question names a specific metric (e.g. "NEV ratio"), evaluate only that \
  metric; do not require coverage of correlated metrics in the same table or \
  framework (e.g. "NEV sensitivity") that the question never mentioned
- Exhaustiveness of representative examples when the key conditions are listed
- The form of expression used in the document — a threshold shown in a \
  regulatory table or figure is sufficient evidence without requiring separate \
  narrative text to confirm it; language such as "may not be necessary when X" \
  is sufficient evidence for "what makes X unnecessary"; a numeric value in a \
  regulatory classification table (e.g., a row labeled "High" with value "Below 4%") \
  is an explicit, unambiguous statement of that threshold — do not say the threshold \
  is "unclear" or "not confirmed" when the table already shows it
- Whether customer-specific mitigating factors (e.g., business explanations, \
  account history) can override a regulatory trigger — if the documents identify \
  the trigger condition AND the required regulatory action, the question is \
  answered; do not require the documents to explicitly resolve how mitigating \
  factors interact with the trigger
- Exhaustive enumeration of all regulatory reporting frameworks when the question \
  asks whether a specific category of obligation applies — if the question asks \
  whether credit unions must collect and submit data on individual loan transactions \
  to a federal agency, and the documents identify the applicable federal requirement \
  and resolve the institution's exemption status, the question is answered; do not \
  require coverage of separate periodic reporting frameworks that serve a different \
  purpose (e.g., aggregate financial condition reports) unless the question \
  explicitly asks about them
- Exhaustive sub-procedure detail within an identified compliance category — if the \
  documents establish that an obligation category applies (e.g., SAR filing, enhanced \
  due diligence, DOR consideration) and explain its key conditions, do not require \
  every sub-procedure, form, or sub-regulation within that category unless the question \
  explicitly names those sub-requirements; identifying the category with its trigger \
  conditions is sufficient; a document noting that certain narrower sub-requirements \
  (e.g., Section 312 of the USA PATRIOT Act) are outside its own scope does not mean \
  those sub-requirements must be covered — it means the document is appropriately \
  scoped, not that the answer is incomplete
- Whether a requirement is "automatic" when the documents already explain the \
  conditions that determine it — if a document states a requirement is determined \
  on a case-by-case basis or lists specific conditions that must be present, this \
  directly answers whether the requirement is automatic (it is not); do not reject \
  because the document does not also add a separate statement saying "this is not \
  automatic" — the conditions already imply that
- Regulatory obligations from frameworks not explicitly referenced in the question — \
  if a corpus document explicitly states that no unique additional requirement applies \
  under a given regulatory rule (e.g., "there is no regulatory requirement for unique \
  additional due diligence steps for PEPs under the CDD rule"), treat that statement \
  as the authoritative answer; do not reject because a different regulatory framework \
  (not asked about in the question) might impose additional requirements; the question \
  asks what the documents say, not what every conceivable regulation might require
- Your own internal reasoning overrides the verdict — if your explanation finds that \
  all dimensions the question asks about are adequately addressed, output YES; do not \
  output NO and then explain that the question's categories are actually covered; the \
  verdict and reasoning must be consistent

Before responding, count the distinct regulatory dimensions this question explicitly \
asks about (each numbered sub-question or named obligation counts as one dimension).

Output format — respond with ONLY a JSON object, no preamble, no trailing text:
{"grading_result": "yes", "feedback": "", "grading_score": 1.0}

Rules:
- "grading_result": "yes" if ALL dimensions are substantively addressed; "no" otherwise
- "feedback": empty string when "yes"; one concise sentence (in regulatory document \
  language, not question language) naming the FIRST unaddressed dimension when "no"
- "grading_score": fraction of total dimensions substantively addressed, as a decimal \
  to two places (e.g., 3 of 5 addressed = 0.60); always 1.0 when grading_result is "yes"\
"""

# Generator is instructed to attribute each claim to a source document and
# explicitly flag any aspect it cannot ground — this tightens faithfulness scores.
# Static role/instructions cached in the system message; context + question as human.
_GENERATOR_SYSTEM = """\
You are a compliance expert specializing in NCUA regulations and community banking law.

Answer the question using ONLY the context documents provided. For each factual \
claim in your answer, identify which document supports it. If any aspect of the \
question cannot be answered from the provided documents, explicitly state: \
"I cannot find guidance on [specific aspect] in the retrieved documents." \
Do not infer from general knowledge.\
"""


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


def rewriter_node(state: AgentState) -> dict:
    llm = _get_llm()
    is_retry = state["retry_count"] > 0 and state["rewritten_query"]
    feedback = state["grader_feedback"] or "The retrieved documents were insufficient."

    # Use best_grader_score (not raw grader_score) so Haiku drift — where the model
    # downgrades a previously confirmed dimension — doesn't falsely trigger stagnation.
    best_score = state.get("best_grader_score", 0.0)
    prev_score = state.get("prev_grader_score", 0.0)  # best score at previous rewriter call

    # Stagnated when the best score hasn't improved since the last rewriter call.
    score_stagnated = (
        state["retry_count"] > 1
        and best_score <= prev_score
        and best_score < 1.0
    )
    is_dead_end = state["last_retrieval_novel_count"] == 0 or score_stagnated

    if not is_retry:
        prompt = _REWRITER_PROMPT_INITIAL.format(query=state["original_query"])
    elif is_dead_end:
        prompt = _REWRITER_PROMPT_DEAD_END.format(
            query=state["original_query"],
            previous_rewrite=state["rewritten_query"],
            grader_feedback=feedback,
        )
    else:
        # Coverage note uses best_score so the message reflects actual peak coverage,
        # not a potentially drift-downgraded snapshot from the latest grader call.
        if best_score >= 0.70:
            coverage_note = (
                f"Coverage so far: {best_score:.0%} — the gap is narrow. "
                "Target only the specific missing dimension above."
            )
        else:
            coverage_note = (
                f"Coverage so far: {best_score:.0%} — current approach is substantially "
                "incomplete. A broader vocabulary shift toward different regulatory "
                "terminology may be needed."
            )
        vocab = _get_manifest_vocabulary(feedback)
        corpus_vocabulary_section = (
            f"CORPUS VOCABULARY for this dimension "
            f"(exact terms from the knowledge base — use these in your query):\n"
            f"{vocab}\n\n"
        ) if vocab else ""
        prompt = _REWRITER_PROMPT_RETRY.format(
            previous_rewrite=state["rewritten_query"],
            grader_feedback=feedback,
            coverage_note=coverage_note,
            corpus_vocabulary_section=corpus_vocabulary_section,
        )

    response = llm.invoke(prompt)
    usage = response.usage_metadata or {}
    rewritten = response.content.strip()
    return {
        "rewritten_query": rewritten,
        # Store current best so next rewriter call can detect whether it improved.
        "prev_grader_score": best_score,
        "step_log": [{"node": "rewriter", "status": "done", "detail": f"Rewrote to: {rewritten}"}],
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def retriever_node(state: AgentState) -> dict:
    vs = _get_vectorstore()
    docs_and_scores = vs.similarity_search_with_relevance_scores(
        state["rewritten_query"], k=config.TOP_K
    )
    new_chunks = _build_chunks(docs_and_scores)

    # Accumulate unique chunks across all retrieval passes (dedup by chunk_id).
    # Generator needs context from every pass — discarding earlier chunks means
    # losing document clusters found before the grader pivoted the query.
    # Tag each novel chunk with its retrieval pass so source_coverage can scope
    # the denominator to cited_docs ∪ final_pass_docs rather than all accumulated docs.
    existing_ids = {c["chunk_id"] for c in state["retrieved_chunks"]}
    pass_number = state["retry_count"]
    novel = [
        {**c, "retrieval_pass": pass_number}
        for c in new_chunks
        if c["chunk_id"] not in existing_ids
    ]
    accumulated = state["retrieved_chunks"] + novel

    sources = ", ".join(dict.fromkeys(c["source_file"] for c in new_chunks))
    detail = f"Retrieved {len(novel)} new chunk(s) from: {sources}"
    if state["retrieved_chunks"]:
        detail += f"  ({len(accumulated)} total across all attempts)"

    return {
        "retrieved_chunks": accumulated,
        "last_retrieval_novel_count": len(novel),
        "step_log": [{"node": "retriever", "status": "done", "detail": detail}],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def grader_node(state: AgentState) -> dict:
    llm = _get_llm()
    # Grader evaluates ALL accumulated chunks — checks whether the full
    # collection covers every dimension, not just the latest retrieval.
    context_str = _build_context_str(state["retrieved_chunks"])
    # Static grader instructions in system message with cache_control so the prefix
    # is reused across all retry calls for the same query (and across queries within
    # the 5-minute TTL window).  Dynamic query + context go in the human message.
    messages = [
        SystemMessage(content=[{
            "type": "text",
            "text": _GRADER_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }]),
        HumanMessage(content=f"Question: {state['original_query']}\n\nRetrieved documents:\n{context_str}"),
    ]
    response = llm.invoke(messages)
    usage = response.usage_metadata or {}
    is_relevant, feedback, score = _parse_grader_response(response.content)
    new_best = max(score, state.get("best_grader_score", 0.0))
    label = "HIGH" if is_relevant else "LOW"
    retry_note = f" (retry {state['retry_count']}/{config.MAX_RETRIES})" if state["retry_count"] > 0 else ""
    score_note = f" | score={score:.2f}"
    detail = f"Relevance: {label}{retry_note}{score_note}"
    if not is_relevant and feedback:
        detail += f" — {feedback}"
    return {
        "grader_relevant": is_relevant,
        "grader_feedback": feedback,
        "grader_score": score,
        "best_grader_score": new_best,
        "step_log": [{"node": "grader", "status": "done", "detail": detail, "score": score}],
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def retry_counter_node(state: AgentState) -> dict:
    new_count = state["retry_count"] + 1
    # Compare best scores across rewriter boundaries: if best_grader_score (updated by grader)
    # exceeds prev_grader_score (set by the previous rewriter call), the score improved.
    improved = state.get("best_grader_score", 0.0) > state.get("prev_grader_score", 0.0)
    stable = 0 if improved else state.get("consecutive_stable_retries", 0) + 1
    return {
        "retry_count": new_count,
        "consecutive_stable_retries": stable,
        "step_log": [{"node": "retry_counter", "status": "done", "detail": f"Retry {new_count}/{config.MAX_RETRIES}"}],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def generator_node(state: AgentState) -> dict:
    llm = _get_generator_llm()
    # Context includes all chunks accumulated across every retrieval pass.
    context_str = _build_context_str(state["retrieved_chunks"])
    messages = [
        SystemMessage(content=[{
            "type": "text",
            "text": _GENERATOR_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }]),
        HumanMessage(content=f"Context:\n{context_str}\n\nQuestion: {state['original_query']}\n\nAnswer:"),
    ]
    response = llm.invoke(messages)
    usage = response.usage_metadata or {}
    return {
        "answer": response.content,
        "step_log": [{"node": "generator", "status": "done", "detail": "Generated answer"}],
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

_graph = None


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("rewriter", rewriter_node)
    g.add_node("retriever", retriever_node)
    g.add_node("grader", grader_node)
    g.add_node("retry_counter", retry_counter_node)
    g.add_node("generator", generator_node)

    g.set_entry_point("rewriter")
    g.add_edge("rewriter", "retriever")
    g.add_edge("retriever", "grader")
    g.add_conditional_edges(
        "grader",
        _route,
        {"generator": "generator", "retry_counter": "retry_counter"},
    )
    g.add_edge("retry_counter", "rewriter")
    g.add_edge("generator", END)
    return g.compile()


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_agentic_rag(query: str) -> AgenticRAGResult:
    t0 = time.perf_counter()

    initial: AgentState = {
        "original_query": query,
        "rewritten_query": "",
        "retrieved_chunks": [],
        "grader_relevant": False,
        "grader_feedback": "",
        "grader_score": 0.0,
        "best_grader_score": 0.0,
        "prev_grader_score": 0.0,
        "consecutive_stable_retries": 0,
        "last_retrieval_novel_count": 0,
        "retry_count": 0,
        "answer": "",
        "step_log": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    final = _get_graph().invoke(initial)

    grader_scores = [
        step["score"]
        for step in final["step_log"]
        if step.get("node") == "grader" and "score" in step
    ]

    return AgenticRAGResult(
        query=query,
        answer=final["answer"],
        chunks=final["retrieved_chunks"],
        step_log=final["step_log"],
        retry_count=final["retry_count"],
        retrieval_confidence=_compute_retrieval_confidence(final["retry_count"]),
        latency_s=time.perf_counter() - t0,
        input_tokens=final["input_tokens"],
        output_tokens=final["output_tokens"],
        grader_scores=grader_scores,
        best_grader_score=final.get("best_grader_score", 0.0),
    )


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    console = Console()
    query = (
        "What is the net worth ratio required to be classified as well-capitalized?"
    )
    console.print(f"\n[bold cyan]Query:[/bold cyan] {query}")
    result = run_agentic_rag(query)

    console.print("\n[bold]Step log:[/bold]")
    for step in result.step_log:
        icon = "✓" if step["status"] == "done" else "✗"
        console.print(f"  {icon} [{step['node'].upper()}] {step['detail']}")

    console.print(f"\n[bold green]Answer:[/bold green] {result.answer}")
    console.print(
        f"[dim]Retries: {result.retry_count} | Confidence: {result.retrieval_confidence:.3f} | "
        f"Tokens: {result.input_tokens}in / {result.output_tokens}out | "
        f"Latency: {result.latency_s:.2f}s[/dim]"
    )

    table = Table(title="Final Chunks", show_lines=True)
    table.add_column("#", width=3)
    table.add_column("Source", style="cyan")
    table.add_column("Similarity", width=10)
    table.add_column("Excerpt", max_width=60)
    for i, chunk in enumerate(result.chunks, 1):
        table.add_row(
            str(i),
            chunk["source_file"],
            f"{chunk['cosine_similarity']:.4f}",
            chunk["text"][:120].replace("\n", " "),
        )
    console.print(table)
