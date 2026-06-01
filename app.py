"""Banking Compliance RAG Demo — Streamlit UI.

Run: streamlit run app.py
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from evaluation.hallucination import HallucinationResult, check_hallucination
from evaluation.quality_score import DimensionScores, QualityScore, compute_quality_score
from pipelines.agentic_rag import (
    AgenticRAGResult,
    AgentState,
    _compute_retrieval_confidence,
    _get_graph,
)
from pipelines.basic_rag import BasicRAGResult, run_basic_rag

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUERIES = [
    "What is the net worth ratio required to be classified as well-capitalized?",
    "What BSA/AML program elements are credit unions required to maintain?",
    "What triggers a SAR filing requirement and what is the filing deadline?",
    "What audit requirements change for a credit union that crosses the $500M asset threshold?",
    "What are the NCUA's expectations for third-party vendor management in credit unions?",
    (
        "One of our members holds a senior government post abroad and has been sending money to the same "
        "overseas business three times this month, each payment just below our standard wire review trigger. "
        "Our team approves each transfer individually. What distinct compliance categories does this pattern "
        "trigger — beyond standard wire transfer procedures — and what would a regulator expect us to have "
        "documented for this account?"
    ),
    (
        "After receiving a High rating for interest rate risk in our last NCUA examination, our "
        "board needs two things answered before our next meeting: (1) What is the specific "
        "post-shock net economic value ratio threshold that NCUA's supervisory test uses to "
        "classify a credit union as High risk? (2) Does a High IRR classification automatically "
        "result in NCUA issuing a formal written supervisory finding or action commitment against "
        "us — or does the exam guidance identify specific situations in which no such formal "
        "written action from NCUA would be expected, even when the High classification applies?"
    ),
    (
        "We just got off the phone with our regional examiner — our net worth closed at 4.5% last "
        "quarter after unexpected loan losses. We know we'll need to submit a restoration plan. "
        "But our board's immediate concern is the loan pipeline: we have $8M in approved commercial "
        "loans ready to close over the next 60 days. Once we're formally classified at this net worth "
        "level, does NCUA regulation require us to pause commercial loan originations, or is that the "
        "examiner's discretion? And is there anything that becomes legally mandatory — not just "
        "recommended — the moment we fall into this capital tier?"
    ),
    (
        "We've been growing our home equity line of credit portfolio and first-lien residential "
        "mortgage originations significantly. We have $340 million in total assets and operate "
        "branch offices in two metropolitan statistical areas. Last year we originated $45 "
        "million in first-lien home purchase and refinancing transactions. Our LTV limits, "
        "collateral valuation standards, appraisal processes, and board risk oversight practices "
        "all follow NCUA guidance for institutions at our concentration level. Our compliance "
        "officer is preparing for our upcoming NCUA examination and wants to ensure our "
        "residential mortgage program is fully compliant. Are there federal obligations specific "
        "to our mortgage origination activities — other than what our NCUA examination covers "
        "— that our compliance program should address?"
    ),
    (
        "We just originated a $2.8M commercial real estate loan secured by the borrower's warehouse. "
        "Our lending officer documented collateral value using an internal property assessment and a "
        "recent comparable sales summary from a local realtor. Does this documentation satisfy "
        "NCUA's collateral valuation requirements for a commercial loan of this size, or is a "
        "different form of valuation required?"
    ),
    (
        "Our exam prep team needs three specific regulatory thresholds confirmed before our NCUA "
        "examination next quarter: (a) What is the exact post-shock NEV ratio percentage below which "
        "a credit union is classified as 'High risk' under NCUA's 2022 revised NEV Supervisory Test "
        "for interest rate risk? (b) Under Part 723, what is the maximum percentage of net worth a "
        "credit union may lend to a single commercial borrower when the amount above the standard "
        "limit is fully secured by readily marketable collateral — and what qualifies as readily "
        "marketable collateral under NCUA's definition? (c) What is the minimum dollar amount of "
        "suspected money laundering activity that triggers mandatory SAR filing when a suspect can "
        "be identified, and how many calendar days after the date of detection does the credit union "
        "have to file the SAR?"
    ),
    (
        "We are preparing to approve a commercial real estate loan totaling $3.2M to a single "
        "borrower. Our net worth is $15M, so this loan would represent approximately 21% of net "
        "worth — above the standard single-borrower limit. Our chief lending officer believes the "
        "borrower's warehouse property secures the loan adequately. Please address three questions: "
        "(a) Under Part 723, what specific conditions must be satisfied to approve a commercial loan "
        "above the standard 15% single-borrower limit, and does commercial real estate — such as a "
        "warehouse — qualify as 'readily marketable collateral' for purposes of that exception? "
        "(b) What appraisal standards must be met for commercial real estate collateral under NCUA "
        "Part 722, and is an internal property assessment or a realtor comparable-sales summary "
        "sufficient? (c) Our commercial real estate portfolio now exceeds 100% of net worth. What "
        "board-approved documentation does NCUA require when concentrations reach this level?"
    ),
]

QUERY_LABELS = [
    "Q1 — Net worth ratio (well-capitalized)",
    "Q2 — BSA/AML program elements",
    "Q3 — SAR filing triggers and deadline",
    "Q4 — $500M asset threshold / audit requirements",
    "Q5 — Third-party vendor management",
    "Q6 — SAR structuring / PEP trap",
    "Q7 — IRR High rating: NEV threshold + formal action conditions",
    "Q8 — Undercapitalized: mandatory commercial lending restrictions",
    "Q9 — HMDA: residential lending reporting obligations",
    "Q10 — Commercial RE appraisal: internal assessment vs. 12 CFR 722",
    "Q11 ★ — Three regulatory thresholds: NEV / single-borrower / SAR",
    "Q12 ★ — CRE loan at 21% NW: Part 723 exception, Part 722 appraisal, concentration",
]

PROFILES = {
    "Compliance-Grade": "compliance_grade",
    "High-Throughput": "high_throughput",
    "Cost-Optimized": "cost_optimized",
}

PROFILE_CAPTIONS = {
    "Compliance-Grade": "Accuracy-first · 50% faithfulness weight",
    "High-Throughput": "Speed-first · 40% latency weight",
    "Cost-Optimized": "Cost-first · 40% cost weight",
}

# ---------------------------------------------------------------------------
# Global CSS  (font size +25%, hand cursor on selects)
# ---------------------------------------------------------------------------

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

/* ── Typography ───────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 15px !important;
}

/* ── Hand cursor on dropdowns ─────────────────────────────────── */
[data-testid="stSelectbox"] *,
[data-testid="stSelectbox"] div[role="combobox"],
[data-testid="stSelectbox"] div[role="option"] {
    cursor: pointer !important;
}

/* ── Pipeline schematic ───────────────────────────────────────── */
.rag-schema {
    display: flex;
    gap: 24px;
    margin: 12px 0 4px;
}
.pipeline {
    flex: 1;
    background: #1E293B;
    border-radius: 8px;
    padding: 16px 20px;
}
.pipeline h4 {
    color: #94A3B8;
    margin: 0 0 14px;
    font-size: 0.82rem;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}
.flow {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
}
.node {
    background: #272F42;
    color: #93C5FD;
    padding: 6px 13px;
    border-radius: 4px;
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
    transition: opacity 150ms ease;
}
.node.result      { color: #22C55E; background: #14291E; }
.node.grader-low  { color: #F59E0B; background: #292214; }
.node.grader-high { color: #22C55E; background: #14291E; }
.arrow            { color: #475569; font-size: 1.1rem; }

/* ── Stacked attempt rows ─────────────────────────────────────── */
.attempts {
    border-left: 2px solid #334155;
    margin: 4px 0 8px 4px;
    padding-left: 0;
}
.attempt {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    transition: opacity 0.4s;
}
.attempt.retry   { opacity: 0.55; }
.attempt.success {
    opacity: 1;
    background: rgba(34, 197, 94, 0.06);
    border-radius: 0 4px 4px 0;
    border-left: 2px solid #22C55E;
    margin-left: -2px;
}
.attempt-label {
    font-size: 0.68rem;
    color: #475569;
    letter-spacing: 1px;
    text-transform: uppercase;
    min-width: 74px;
    flex-shrink: 0;
}
.attempt.success .attempt-label { color: #22C55E; }
.retry-spin {
    font-size: 1.1rem;
    color: #F59E0B;
    animation: retry-pulse 1.6s ease-in-out infinite;
}
/* Cycle the active row highlight every 4s */
.attempt.retry:nth-child(1) { animation: row-cycle 4s 0s ease-in-out infinite; }
.attempt.retry:nth-child(2) { animation: row-cycle 4s 2s ease-in-out infinite; }
@keyframes row-cycle {
    0%,40%  { opacity: 0.85; }
    60%,100%{ opacity: 0.35; }
}
@keyframes retry-pulse {
    0%,100% { opacity: 0.2; }
    50%     { opacity: 1.0; }
}
.schema-caption {
    color: #475569;
    font-size: 0.75rem;
    margin: 6px 0 0;
}

/* ── Step log waiting state ───────────────────────────────────── */
.step-waiting {
    color: #475569;
    font-size: 0.85rem;
    font-style: italic;
    padding: 4px 0;
}
</style>
"""

# ---------------------------------------------------------------------------
# Intro schematic
# ---------------------------------------------------------------------------

_INTRO_HTML = (
    '<div class="rag-schema">'
      '<div class="pipeline">'
        '<h4>Basic RAG</h4>'
        '<div class="flow">'
          '<div class="node">Query</div>'
          '<div class="arrow">→</div>'
          '<div class="node">Retriever</div>'
          '<div class="arrow">→</div>'
          '<div class="node">Generator</div>'
          '<div class="arrow">→</div>'
          '<div class="node result">Answer</div>'
        '</div>'
        '<p class="schema-caption">'
          'Single shot &nbsp;&middot;&nbsp; no quality gate &nbsp;&middot;&nbsp; confidence via cosine similarity'
        '</p>'
      '</div>'
      '<div class="pipeline">'
        '<h4>Agentic RAG</h4>'
        '<div class="attempts">'
          '<div class="attempt retry">'
            '<span class="attempt-label">Attempt 1</span>'
            '<div class="flow">'
              '<div class="node">Rewriter</div>'
              '<div class="arrow">→</div>'
              '<div class="node">Retriever</div>'
              '<div class="arrow">→</div>'
              '<div class="node grader-low">Grader: LOW</div>'
              '<span class="retry-spin">↺</span>'
            '</div>'
          '</div>'
          '<div class="attempt retry">'
            '<span class="attempt-label">Attempt 2</span>'
            '<div class="flow">'
              '<div class="node">Rewriter</div>'
              '<div class="arrow">→</div>'
              '<div class="node">Retriever</div>'
              '<div class="arrow">→</div>'
              '<div class="node grader-low">Grader: LOW</div>'
              '<span class="retry-spin" style="animation-delay:0.8s">↺</span>'
            '</div>'
          '</div>'
          '<div class="attempt success">'
            '<span class="attempt-label">Attempt 3</span>'
            '<div class="flow">'
              '<div class="node">Rewriter</div>'
              '<div class="arrow">→</div>'
              '<div class="node">Retriever</div>'
              '<div class="arrow">→</div>'
              '<div class="node grader-high">Grader: HIGH</div>'
              '<div class="arrow">→</div>'
              '<div class="node">Generator</div>'
              '<div class="arrow">→</div>'
              '<div class="node result">Answer ✓</div>'
            '</div>'
          '</div>'
        '</div>'
        '<p class="schema-caption">'
          'Query rewritten on each retry &nbsp;&middot;&nbsp; LLM grader validates relevance &nbsp;&middot;&nbsp; retry budget enforced'
        '</p>'
      '</div>'
    '</div>'
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------


def _init_state() -> None:
    if "results" not in st.session_state:
        # {query_idx: {basic_result, agentic_result, basic_hal, agentic_hal}}
        st.session_state.results = {}


# ---------------------------------------------------------------------------
# Step rendering helpers
# ---------------------------------------------------------------------------

_STEP_ICONS = {
    "rewriter": ("✓", "REWRITER"),
    "retriever": ("✓", "RETRIEVER"),
    "generator": ("✓", "GENERATOR"),
}


def _step_to_markdown(step: dict) -> str:
    node = step["node"]
    detail = step["detail"]
    if node == "grader":
        icon = "✗" if "LOW" in detail else "✓"
        return f"{icon} **[GRADER]** {detail}"
    if node == "retry_counter":
        return f"↺ **{detail}**"
    icon, label = _STEP_ICONS.get(node, ("·", node.upper()))
    return f"{icon} **[{label}]** {detail}"


def _render_steps(steps: list[dict]) -> str:
    if not steps:
        return "<div class='step-waiting'>Waiting for first step…</div>"
    return "  \n".join(_step_to_markdown(s) for s in steps)


# ---------------------------------------------------------------------------
# Badge + claims rendering
# ---------------------------------------------------------------------------


def _render_badge(container, hal: HallucinationResult) -> None:
    with container.container():
        if hal.faithfulness_score is None:
            st.warning("**?** Grounding check unavailable")
        elif hal.has_warning:
            n_unsourced = sum(1 for c in hal.claims if not c.sourced)
            score_pct = f"{hal.faithfulness_score:.0%}"
            st.error(f"**⚠ {n_unsourced} unsourced claim(s) detected** (faithfulness: {score_pct})")
        else:
            n = len(hal.claims)
            st.success(f"**✓ All {n} claim{'s' if n != 1 else ''} sourced** (faithfulness: 100%)")

        if hal.claims and hal.faithfulness_score is not None:
            n = len(hal.claims)
            with st.expander(f"ℹ  Show {n} claim{'s' if n != 1 else ''}"):
                for c in hal.claims:
                    icon = "✓" if c.sourced else "✗"
                    colour = "green" if c.sourced else "red"
                    chunk_ref = f"  \n  `{c.evidence_chunk_id}`" if c.evidence_chunk_id else ""
                    st.markdown(
                        f"<span style='color:{colour}'><b>{icon}</b></span>&nbsp; {c.claim}{chunk_ref}",
                        unsafe_allow_html=True,
                    )
                    st.divider()


# ---------------------------------------------------------------------------
# Score display
# ---------------------------------------------------------------------------


def _score_bar(label: str, score: float, delta: float | None = None) -> None:
    col_label, col_bar, col_num = st.columns([2, 5, 1])
    with col_label:
        st.write(label)
    with col_bar:
        filled = max(0.0, min(1.0, score)) * 100
        st.markdown(
            f"<div style='"
            f"width:100%;height:26px;border-radius:4px;position:relative;overflow:hidden;"
            f"background-color:#0F172A;"
            f"background-image:radial-gradient(circle,#1E293B 1.5px,transparent 1.5px);"
            f"background-size:7px 7px;'>"
            f"<div style='"
            f"width:{filled}%;height:100%;position:absolute;left:0;top:0;"
            f"background:#3B82F6;border-radius:4px 0 0 4px;'>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with col_num:
        if delta is not None:
            arrow = "↑" if delta >= 0 else "↓"
            pts = abs(delta) * 100
            colour = "#22C55E" if delta >= 0 else "#F59E0B"
            st.markdown(
                f"**{score:.2f}** <span style='color:{colour};font-size:0.8em'>{arrow} {pts:.1f} pts</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"**{score:.2f}**")


def _render_dimension_table(dims: DimensionScores) -> None:
    st.metric("Accuracy", f"{dims.accuracy:.2f}")
    st.metric("Source coverage", f"{dims.source_coverage:.2f}")
    st.metric("Retrieval confidence", f"{dims.retrieval_confidence:.2f}")
    st.metric("Latency", f"{dims.latency:.2f}")
    st.metric("Cost", f"{dims.cost:.2f}")


def _render_score_section(
    basic_result: BasicRAGResult,
    agentic_result: AgenticRAGResult,
    basic_hal: HallucinationResult,
    agentic_hal: HallucinationResult,
    profile_key: str,
    profile_label: str,
) -> None:
    bqs = compute_quality_score(basic_result, basic_hal, profile=profile_key)
    aqs = compute_quality_score(agentic_result, agentic_hal, profile=profile_key)
    gap = aqs.composite - bqs.composite

    st.divider()
    st.subheader("Retrieval Quality Score")
    st.caption(f"Profile: **{profile_label}**")

    _score_bar("Basic RAG", bqs.composite)
    _score_bar("Agentic RAG", aqs.composite, delta=gap)

    with st.expander("Dimension breakdown"):
        dc, ac = st.columns(2)
        with dc:
            st.caption("Basic RAG")
            _render_dimension_table(bqs.dimensions)
        with ac:
            st.caption("Agentic RAG")
            _render_dimension_table(aqs.dimensions)

    conf_label_basic = "cosine proxy"
    conf_label_agentic = "LLM grader"
    st.caption(
        f"Basic retrieval confidence ({conf_label_basic}): **{basic_result.retrieval_confidence:.3f}** · "
        f"Agentic retrieval confidence ({conf_label_agentic}): **{agentic_result.retrieval_confidence:.3f}** · "
        f"Agentic retries: **{agentic_result.retry_count}**"
    )


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


def _render_leaderboard(profile_key: str) -> None:
    if not st.session_state.results:
        return

    st.divider()
    st.subheader("Query Leaderboard")

    for q_idx in sorted(st.session_state.results):
        data = st.session_state.results[q_idx]
        bqs = compute_quality_score(data["basic_result"], data["basic_hal"], profile=profile_key)
        aqs = compute_quality_score(data["agentic_result"], data["agentic_hal"], profile=profile_key)
        gap = aqs.composite - bqs.composite
        retries = data["agentic_result"].retry_count

        lbl_col, ret_col = st.columns([9, 1])
        with lbl_col:
            st.markdown(f"**{QUERY_LABELS[q_idx]}**")
        with ret_col:
            st.caption(f"↺ {retries}" if retries else "—")

        _score_bar("Basic RAG", bqs.composite)
        _score_bar("Agentic RAG", aqs.composite, delta=gap)
        st.write("")


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------


def _run_basic(query: str, answer_area, status_area) -> BasicRAGResult:
    status_area.info("🔍 Retrieving and generating…")
    result = run_basic_rag(query)
    status_area.empty()
    answer_area.markdown(result.answer)
    return result


def _run_agentic_streaming(
    query: str, steps_area, answer_area
) -> AgenticRAGResult | None:
    steps_area.markdown(_render_steps([]), unsafe_allow_html=True)

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

    t0 = time.perf_counter()
    graph = _get_graph()
    final_state: AgentState | None = None

    try:
        for state_snapshot in graph.stream(initial, stream_mode="values"):
            final_state = state_snapshot
            steps_area.markdown(
                _render_steps(state_snapshot.get("step_log", [])),
                unsafe_allow_html=True,
            )
    except Exception as exc:
        steps_area.error(f"Agentic pipeline error: {exc}")
        return None

    if final_state is None:
        steps_area.error("Agentic pipeline produced no output.")
        return None

    latency = time.perf_counter() - t0
    answer_area.markdown(final_state["answer"])

    return AgenticRAGResult(
        query=query,
        answer=final_state["answer"],
        chunks=final_state["retrieved_chunks"],
        step_log=final_state["step_log"],
        retry_count=final_state["retry_count"],
        retrieval_confidence=_compute_retrieval_confidence(final_state["retry_count"]),
        latency_s=latency,
        input_tokens=final_state["input_tokens"],
        output_tokens=final_state["output_tokens"],
    )


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="Banking Compliance RAG Showcase",
        page_icon="🏦",
        layout="wide",
    )
    _init_state()

    # Inject global CSS (font size, cursors, schema styles)
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    # Check required env vars early
    missing = [k for k in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY") if not os.getenv(k)]
    if missing:
        st.error(f"Missing environment variables: {', '.join(missing)}. Add them to .env and restart.")
        st.stop()

    # ── Header ──────────────────────────────────────────────────────────────
    st.title("Banking Compliance RAG Showcase")
    #st.caption("Basic RAG vs Agentic RAG on NCUA regulatory queries")

    # ── Intro schematic (expanded on load) ───────────────────────────────────
    with st.expander("Basic vs Agentic RAG", expanded=True):
        st.markdown(_INTRO_HTML, unsafe_allow_html=True)

    # ── Interactive demo (collapsed on load) ─────────────────────────────────
    with st.expander("▶ Try it out", expanded=False):

        # Control bar
        ctrl_q, ctrl_p, ctrl_btn = st.columns([4, 2, 1])

        with ctrl_q:
            query_label = st.selectbox("Query", options=QUERY_LABELS)
        with ctrl_p:
            profile_label = st.selectbox("Profile", options=list(PROFILES.keys()))
            st.caption(PROFILE_CAPTIONS[profile_label])
        with ctrl_btn:
            st.write("")  # align button with selectbox baseline
            run_clicked = st.button("Run", type="primary", use_container_width=True)

        query_idx = QUERY_LABELS.index(query_label)
        query = QUERIES[query_idx]
        profile_key = PROFILES[profile_label]

        # Full query display
        st.markdown(
            f"<div style='color:#94A3B8; font-size:0.85rem; margin:4px 0 16px; "
            f"padding:10px 16px; border-left:3px solid #334155; background:#1E293B; "
            f"border-radius:0 6px 6px 0;'>"
            f"<span style='color:#475569; font-size:0.7rem; letter-spacing:1px; "
            f"text-transform:uppercase; display:block; margin-bottom:6px;'>Full query</span>"
            f"{query}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Two-column answer panes
        col_basic, col_agentic = st.columns(2)

        with col_basic:
            st.subheader("Basic RAG")
            basic_status = st.empty()
            basic_answer = st.empty()
            basic_badge = st.empty()

        with col_agentic:
            st.subheader("Agentic RAG")
            agentic_steps = st.empty()
            agentic_answer = st.empty()
            agentic_badge = st.empty()

        # Run logic
        if run_clicked:
            for area in (basic_status, basic_answer, basic_badge,
                          agentic_steps, agentic_answer, agentic_badge):
                area.empty()

            basic_result = _run_basic(query, basic_answer, basic_status)

            agentic_result = _run_agentic_streaming(query, agentic_steps, agentic_answer)
            if agentic_result is None:
                st.stop()

            with st.spinner("Checking claim grounding…"):
                basic_hal = check_hallucination(query, basic_result.answer, basic_result.chunks)
                agentic_hal = check_hallucination(query, agentic_result.answer, agentic_result.chunks)

            _render_badge(basic_badge, basic_hal)
            _render_badge(agentic_badge, agentic_hal)

            st.session_state.results[query_idx] = {
                "basic_result": basic_result,
                "agentic_result": agentic_result,
                "basic_hal": basic_hal,
                "agentic_hal": agentic_hal,
            }

        elif query_idx in st.session_state.results:
            data = st.session_state.results[query_idx]
            basic_answer.markdown(data["basic_result"].answer)
            agentic_steps.markdown(
                _render_steps(data["agentic_result"].step_log),
                unsafe_allow_html=True,
            )
            agentic_answer.markdown(data["agentic_result"].answer)
            _render_badge(basic_badge, data["basic_hal"])
            _render_badge(agentic_badge, data["agentic_hal"])

        else:
            with col_basic:
                basic_status.info("Select a query and click Run to compare pipelines.")
            with col_agentic:
                agentic_steps.markdown(
                    "<div class='step-waiting'>Agentic steps will stream here in real time.</div>",
                    unsafe_allow_html=True,
                )

        # Score section
        if query_idx in st.session_state.results:
            data = st.session_state.results[query_idx]
            _render_score_section(
                data["basic_result"],
                data["agentic_result"],
                data["basic_hal"],
                data["agentic_hal"],
                profile_key=profile_key,
                profile_label=profile_label,
            )

        # Leaderboard anchor
        if len(st.session_state.results) > 0:
            st.info("Query Leaderboard updated — scroll down to compare all runs.")

        # Leaderboard
        _render_leaderboard(profile_key)


if __name__ == "__main__":
    main()
