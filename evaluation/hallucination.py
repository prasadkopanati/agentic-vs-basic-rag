"""LLM-as-judge hallucination checker.

Single prompt call: extracts atomic factual claims from an answer, then
judges each claim against the retrieved source chunks. Returns a
faithfulness_score (supported / total) in [0,1].

Graceful degradation: on any LLM failure, returns HallucinationResult
with faithfulness_score=None, has_warning=None — UI shows a ? badge.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

from langchain_anthropic import ChatAnthropic

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ClaimResult:
    claim: str
    sourced: bool
    evidence_chunk_id: str | None


@dataclass
class HallucinationResult:
    claims: list[ClaimResult]
    faithfulness_score: float | None  # None = checker unavailable
    has_warning: bool | None          # None = checker unavailable


# ---------------------------------------------------------------------------
# Pure-logic helpers (exported for unit testing)
# ---------------------------------------------------------------------------


def _compute_faithfulness(claims: list[ClaimResult]) -> float:
    """Return supported_claims / total_claims; 1.0 if no claims (vacuously clean)."""
    if not claims:
        return 1.0
    return sum(1 for c in claims if c.sourced) / len(claims)


def _parse_judge_response(text: str) -> list[ClaimResult]:
    """Parse the JSON array returned by the judge prompt into ClaimResult objects."""
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Judge response was not valid JSON: %s", text[:200])
        return []

    if not isinstance(raw, list):
        return []

    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        results.append(
            ClaimResult(
                claim=str(item.get("claim", "")),
                sourced=bool(item.get("sourced", False)),
                evidence_chunk_id=item.get("evidence_chunk_id") or None,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = """\
You are a hallucination checker for a banking compliance Q&A system.

Your task:
1. Extract every atomic factual claim from the Answer below
2. For each claim, decide if it is directly supported by one of the Source Documents
3. Return ONLY a JSON array — no preamble, no explanation

Rules:
- A claim is "sourced" only if the specific fact appears verbatim or by direct inference in a source document
- Do NOT use external knowledge — judge only against the provided documents
- Conditional claims count as one claim (e.g. "SAR required if amount ≥ $5,000" is one claim)
- Set evidence_chunk_id to the chunk_id of the supporting document, or null if unsourced
- SKIP any statement that describes what the answer could NOT find or what the documents do NOT contain — phrases like "I cannot find guidance on X", "The provided documents contain no references to X", "X is not addressed in the retrieved documents", "I don't have enough information about X" describe retrieval coverage, not verifiable regulatory facts; omit them entirely from the claim list

Return format (JSON array only):
[
  {{"claim": "...", "sourced": true, "evidence_chunk_id": "chunk_id_here"}},
  {{"claim": "...", "sourced": false, "evidence_chunk_id": null}}
]

Question: {question}

Answer to evaluate:
{answer}

Source Documents:
{context}"""


def _build_judge_context(chunks: list[dict]) -> str:
    parts = []
    for chunk in chunks:
        parts.append(
            f"[{chunk['chunk_id']}] ({chunk['source_file']})\n{chunk['text']}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_hallucination(
    question: str,
    answer: str,
    chunks: list[dict],
) -> HallucinationResult:
    """Check answer faithfulness against retrieved chunks.

    Returns HallucinationResult with faithfulness_score=None on any LLM failure.
    """
    _DEGRADED = HallucinationResult(claims=[], faithfulness_score=None, has_warning=None)

    if not answer.strip():
        return _DEGRADED

    context = _build_judge_context(chunks)
    prompt = _JUDGE_PROMPT.format(question=question, answer=answer, context=context)

    try:
        llm = ChatAnthropic(
            model=config.LLM_MODEL,
            api_key=os.environ["ANTHROPIC_API_KEY"],
            temperature=0,
            max_tokens=2048,
        )
        response = llm.invoke(prompt)
        claims = _parse_judge_response(response.content)
    except Exception as exc:
        log.error("Hallucination checker failed: %s", exc)
        return _DEGRADED

    if not claims:
        # Empty parse (bad JSON or empty array) — degrade rather than falsely reporting clean
        faithfulness = 1.0 if not answer.strip() else None
        has_warning = None if faithfulness is None else False
        return HallucinationResult(claims=[], faithfulness_score=faithfulness, has_warning=has_warning)

    score = _compute_faithfulness(claims)
    return HallucinationResult(
        claims=claims,
        faithfulness_score=score,
        has_warning=score < 1.0,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from dotenv import load_dotenv

    load_dotenv()
    console = Console()

    question = "What is the net worth ratio to be classified as well-capitalized?"
    answer = (
        "A credit union must maintain a net worth ratio of at least 7% to be classified "
        "as well-capitalized under NCUA's prompt corrective action framework. "
        "Additionally, credit unions must hold at least 10% Tier 1 capital under Basel III."
    )
    chunks = [
        {
            "chunk_id": "risk-based-capital-faqs-df993f.md_42",
            "source_file": "risk-based-capital-faqs-df993f.md",
            "text": (
                "An insured credit union is 'well capitalized' if it has a net worth ratio "
                "of not less than 7 percent and meets any applicable risk-based net worth requirement."
            ),
            "source_url": "",
        }
    ]

    console.print(f"\n[bold cyan]Question:[/bold cyan] {question}")
    console.print(f"[bold]Answer:[/bold] {answer}\n")

    result = check_hallucination(question, answer, chunks)

    if result.faithfulness_score is None:
        console.print("[yellow]? Grounding check unavailable[/yellow]")
    elif result.has_warning:
        console.print(f"[red]⚠ {sum(1 for c in result.claims if not c.sourced)} unsourced claim(s) detected[/red]")
    else:
        console.print(f"[green]✓ All {len(result.claims)} claims sourced[/green]")

    console.print(f"Faithfulness score: {result.faithfulness_score}")

    table = Table(title="Claims", show_lines=True)
    table.add_column("Sourced", width=8)
    table.add_column("Claim")
    table.add_column("Evidence chunk", style="dim")
    for c in result.claims:
        icon = "[green]✓[/green]" if c.sourced else "[red]✗[/red]"
        table.add_row(icon, c.claim, c.evidence_chunk_id or "—")
    console.print(table)
