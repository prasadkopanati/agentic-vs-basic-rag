#!/usr/bin/env python
"""Capture a demo session: run both RAG pipelines and save results to JSON.

Usage:
    uv run python scripts/capture_session.py                   # all 10 queries
    uv run python scripts/capture_session.py --queries Q1,Q3   # subset
    uv run python scripts/capture_session.py --dry-run         # no LLM calls
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Queries — mirrors app.py QUERIES list (keep in sync if app.py changes)
# ---------------------------------------------------------------------------

QUERIES: list[str] = [
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
]


# ---------------------------------------------------------------------------
# Pure helpers (exported for unit testing — no LLM or I/O dependencies)
# ---------------------------------------------------------------------------


def parse_query_ids(ids_str: str | None, total: int) -> list[int]:
    """Parse "Q1,Q3,Q9" into zero-based indices [0, 2, 8].

    Returns all indices when ids_str is None or empty.
    """
    if not ids_str:
        return list(range(total))
    indices: list[int] = []
    for token in ids_str.split(","):
        token = token.strip().upper()
        if not token.startswith("Q"):
            raise ValueError(
                f"Invalid query ID: {token!r} — expected format Q1, Q3, etc."
            )
        try:
            num = int(token[1:])
        except ValueError:
            raise ValueError(
                f"Invalid query ID: {token!r} — expected format Q1, Q3, etc."
            )
        if not (1 <= num <= total):
            raise ValueError(
                f"Query ID {token!r} out of range (Q1–Q{total})"
            )
        indices.append(num - 1)
    return indices


def result_fields(result: Any) -> dict:
    """Extract serializable fields from a BasicRAGResult or AgenticRAGResult."""
    return {
        "answer": result.answer,
        "chunks": result.chunks,
        "latency_s": result.latency_s,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "retrieval_confidence": result.retrieval_confidence,
        "retry_count": getattr(result, "retry_count", 0),
        "grader_scores": getattr(result, "grader_scores", []),
    }


def score_to_dict(score: Any) -> dict:
    """Serialize a QualityScore to a plain dict."""
    return {
        "composite": score.composite,
        "profile": score.profile,
        "dimensions": dataclasses.asdict(score.dimensions),
    }


def hallucination_to_dict(h: Any) -> dict:
    """Serialize a HallucinationResult to a plain dict."""
    return {
        "faithfulness_score": h.faithfulness_score,
        "has_warning": h.has_warning,
        "claims": [
            {
                "claim": c.claim,
                "sourced": c.sourced,
                "evidence_chunk_id": c.evidence_chunk_id,
            }
            for c in h.claims
        ],
    }


def make_dry_run_entry(query_id: str, query_text: str) -> dict:
    """Return a zeroed mock session entry for dry-run mode (no LLM calls)."""
    zero_result = {
        "answer": "[dry-run: no LLM call]",
        "chunks": [],
        "latency_s": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "retrieval_confidence": 0.0,
        "retry_count": 0,
        "grader_scores": [],
    }
    zero_score = {
        "composite": 0.0,
        "profile": "compliance_grade",
        "dimensions": {
            "accuracy": 0.0,
            "source_coverage": 0.0,
            "retrieval_confidence": 0.0,
            "latency": 0.0,
            "cost": 0.0,
        },
    }
    zero_hallucination: dict = {
        "faithfulness_score": None,
        "has_warning": None,
        "claims": [],
    }
    return {
        "query_id": query_id,
        "query_text": query_text,
        "basic": {**zero_result},
        "agentic": {**zero_result},
        "basic_score": {**zero_score},
        "agentic_score": {**zero_score},
        "basic_hallucination": {**zero_hallucination},
        "agentic_hallucination": {**zero_hallucination},
    }


# ---------------------------------------------------------------------------
# Live query runner (imports deferred — not needed for unit tests)
# ---------------------------------------------------------------------------


def _run_query(query_id: str, query_text: str) -> dict:
    """Run both pipelines on one query; return a session entry dict.

    On any exception, returns an entry with an `error` field.
    """
    from rich.console import Console

    from evaluation.hallucination import check_hallucination
    from evaluation.quality_score import compute_quality_score
    from pipelines.agentic_rag import run_agentic_rag
    from pipelines.basic_rag import run_basic_rag

    console = Console()

    entry: dict = {
        "query_id": query_id,
        "query_text": query_text,
    }

    try:
        console.print(f"  [dim]Running {query_id} (basic)…[/dim]")
        basic = run_basic_rag(query_text)
        basic_hall = check_hallucination(query_text, basic.answer, basic.chunks)
        basic_score = compute_quality_score(basic, basic_hall)

        console.print(f"  [dim]Running {query_id} (agentic)…[/dim]")
        agentic = run_agentic_rag(query_text)
        agentic_hall = check_hallucination(query_text, agentic.answer, agentic.chunks)
        agentic_score = compute_quality_score(agentic, agentic_hall)

        entry.update(
            {
                "basic": result_fields(basic),
                "agentic": result_fields(agentic),
                "basic_score": score_to_dict(basic_score),
                "agentic_score": score_to_dict(agentic_score),
                "basic_hallucination": hallucination_to_dict(basic_hall),
                "agentic_hallucination": hallucination_to_dict(agentic_hall),
            }
        )
    except Exception as exc:
        console.print(f"  [red]ERROR {query_id}: {exc}[/red]")
        entry["error"] = str(exc)

    return entry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Capture a RAG demo session to JSON for carousel generation."
    )
    parser.add_argument(
        "--queries",
        metavar="Q1,Q3",
        default=None,
        help="Comma-separated query IDs to run (default: all). Example: Q1,Q3,Q9",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls; write zeroed mock JSON (for carousel development).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Output file path (default: artifacts/session_YYYYMMDD_HHMMSS.json).",
    )
    args = parser.parse_args(argv)

    from rich.console import Console

    console = Console()

    indices = parse_query_ids(args.queries, len(QUERIES))
    selected = [(f"Q{i + 1}", QUERIES[i]) for i in indices]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else Path("artifacts") / f"session_{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "[yellow]DRY RUN[/yellow]" if args.dry_run else "[green]LIVE[/green]"
    console.print(f"\n[bold]Capturing {len(selected)} quer{'y' if len(selected) == 1 else 'ies'} — {mode}[/bold]\n")

    entries: list[dict] = []
    for query_id, query_text in selected:
        console.print(f"[bold]{query_id}[/bold]")
        if args.dry_run:
            entry = make_dry_run_entry(query_id, query_text)
        else:
            entry = _run_query(query_id, query_text)
        entries.append(entry)

    session = {
        "captured_at": timestamp,
        "rag_env": os.getenv("RAG_ENV", "dev"),
        "query_count": len(entries),
        "queries": entries,
    }

    output_path.write_text(json.dumps(session, indent=2, ensure_ascii=False))
    console.print(f"\n[green]✓[/green] Session saved → {output_path}")


if __name__ == "__main__":
    main()
