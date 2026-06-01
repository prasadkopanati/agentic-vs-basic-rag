"""Five-dimension weighted quality score.

Works duck-typed on BasicRAGResult and AgenticRAGResult — both expose
retrieval_confidence, latency_s, input_tokens, output_tokens, and chunks.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from evaluation.hallucination import ClaimResult, HallucinationResult

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class DimensionScores:
    accuracy: float            # best_grader_score (agentic) or faithfulness_score (basic)
    source_coverage: float     # fraction of retrieved source documents cited in supported claims
    retrieval_confidence: float
    latency: float
    cost: float


@dataclass
class QualityScore:
    composite: float
    dimensions: DimensionScores
    profile: str


# ---------------------------------------------------------------------------
# Pure dimension helpers (exported for unit testing)
# ---------------------------------------------------------------------------


def _compute_latency_score(latency_s: float) -> float:
    return max(0.0, 1.0 - latency_s / config.LATENCY_CEILING)


def _compute_cost_score(input_tokens: int, output_tokens: int) -> float:
    cost = config.estimate_cost(input_tokens, output_tokens)
    return max(0.0, 1.0 - cost / config.COST_CEILING)


def _compute_source_coverage(claims: list[ClaimResult], chunks: list[dict]) -> float:
    """Fraction of retrieved source documents cited in at least one supported claim.

    Uses document-level deduplication: multiple chunks from the same source file
    count as one document.

    For iterative pipelines (chunks carry a `retrieval_pass` field), the denominator
    is scoped to `cited_docs ∪ final_pass_docs` rather than all accumulated docs.
    This avoids penalising exploratory retrieval passes that were necessary to navigate
    to the correct document cluster — only unused docs from the final (most targeted)
    pass contribute to the denominator. Single-shot pipelines (no `retrieval_pass`)
    use all unique source files as the denominator.
    """
    if not claims or not chunks:
        return 0.0
    chunk_to_doc = {c["chunk_id"]: c["source_file"] for c in chunks}
    cited_docs = {
        chunk_to_doc[cl.evidence_chunk_id]
        for cl in claims
        if cl.sourced and cl.evidence_chunk_id and cl.evidence_chunk_id in chunk_to_doc
    }
    if any("retrieval_pass" in c for c in chunks):
        final_pass = max(c["retrieval_pass"] for c in chunks if "retrieval_pass" in c)
        final_pass_docs = {c["source_file"] for c in chunks if c.get("retrieval_pass") == final_pass}
        unique_docs = cited_docs | final_pass_docs
    else:
        unique_docs = {c["source_file"] for c in chunks}
    if not unique_docs:
        return 0.0
    return min(1.0, len(cited_docs) / len(unique_docs))


def _compute_composite(dimensions: DimensionScores, weights: dict[str, float]) -> float:
    return (
        weights["accuracy"] * dimensions.accuracy
        + weights["source_coverage"] * dimensions.source_coverage
        + weights["retrieval_confidence"] * dimensions.retrieval_confidence
        + weights["latency"] * dimensions.latency
        + weights["cost"] * dimensions.cost
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_NEUTRAL_ACCURACY = 0.5  # used when hallucination checker was unavailable


def compute_quality_score(
    result,  # BasicRAGResult | AgenticRAGResult (duck-typed)
    hallucination_result: HallucinationResult,
    profile: str = "compliance_grade",
) -> QualityScore:
    weights = config.WEIGHT_PROFILES[profile]

    # For agentic pipeline (has non-empty grader_scores), use best_grader_score as accuracy:
    # the grader explicitly verifies whether all question dimensions are covered, making it
    # a direct completeness signal. For basic pipeline, fall back to faithfulness_score.
    grader_scores = getattr(result, 'grader_scores', None)
    if grader_scores:
        accuracy = result.best_grader_score
    elif hallucination_result.faithfulness_score is not None:
        accuracy = hallucination_result.faithfulness_score
    else:
        accuracy = _NEUTRAL_ACCURACY

    source_coverage = _compute_source_coverage(
        hallucination_result.claims,
        chunks=result.chunks,
    )

    dimensions = DimensionScores(
        accuracy=accuracy,
        source_coverage=source_coverage,
        retrieval_confidence=result.retrieval_confidence,
        latency=_compute_latency_score(result.latency_s),
        cost=_compute_cost_score(result.input_tokens, result.output_tokens),
    )

    composite = _compute_composite(dimensions, weights)

    return QualityScore(composite=composite, dimensions=dimensions, profile=profile)
