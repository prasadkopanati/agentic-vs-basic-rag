"""E2E tests for the evaluation layer.

Calls real Anthropic API. Requires ANTHROPIC_API_KEY and VOYAGE_API_KEY.

Run with: pytest -m e2e
"""

import pytest

from pipelines.basic_rag import run_basic_rag
from pipelines.agentic_rag import run_agentic_rag
from evaluation.hallucination import HallucinationResult, check_hallucination
from evaluation.quality_score import QualityScore, compute_quality_score


_Q1 = "What is the net worth ratio required to be classified as well-capitalized?"
_Q4 = "What audit requirements change for a credit union that crosses the $500M asset threshold?"


@pytest.fixture(autouse=True)
def reset_caches():
    import pipelines.basic_rag as br
    import pipelines.agentic_rag as ar
    orig_vs, orig_llm, orig_graph = br._vs, ar._llm, ar._graph
    br._vs = None
    ar._llm = None
    ar._graph = None
    yield
    br._vs = orig_vs
    ar._llm = orig_llm
    ar._graph = orig_graph


@pytest.mark.e2e
class TestHallucinationCheckerE2E:
    def test_returns_hallucination_result(self):
        result = run_basic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        assert isinstance(hal, HallucinationResult)

    def test_faithfulness_score_in_range_or_none(self):
        result = run_basic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        if hal.faithfulness_score is not None:
            assert 0.0 <= hal.faithfulness_score <= 1.0

    def test_refusal_answer_is_clean(self):
        """Q4 produces a refusal — no factual claims to dispute → faithfulness 1.0."""
        result = run_basic_rag(_Q4)
        hal = check_hallucination(_Q4, result.answer, result.chunks)
        # A clean refusal makes no unsourced claims
        if hal.faithfulness_score is not None:
            assert hal.faithfulness_score == pytest.approx(1.0)

    def test_has_warning_consistent_with_faithfulness(self):
        result = run_basic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        if hal.faithfulness_score is not None and hal.has_warning is not None:
            if hal.faithfulness_score < 1.0:
                assert hal.has_warning is True
            else:
                assert hal.has_warning is False

    def test_graceful_degradation_does_not_raise(self):
        """Even if something goes wrong the function must return, never raise."""
        # Use an empty answer to trigger the edge case
        result = check_hallucination(_Q1, "", [])
        assert isinstance(result, HallucinationResult)


@pytest.mark.e2e
class TestQualityScoreE2E:
    def test_basic_rag_returns_quality_score(self):
        result = run_basic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        qs = compute_quality_score(result, hal)
        assert isinstance(qs, QualityScore)
        assert 0.0 <= qs.composite <= 1.0

    def test_agentic_rag_returns_quality_score(self):
        result = run_agentic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        qs = compute_quality_score(result, hal)
        assert isinstance(qs, QualityScore)
        assert 0.0 <= qs.composite <= 1.0

    def test_agentic_q1_retrieval_confidence_higher_than_basic(self):
        """Agentic retrieval_confidence (1.0, grader-derived) > basic cosine proxy (~0.57)."""
        basic = run_basic_rag(_Q1)
        agentic = run_agentic_rag(_Q1)
        assert agentic.retrieval_confidence > basic.retrieval_confidence

    def test_dimension_scores_in_unit_interval(self):
        result = run_basic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        qs = compute_quality_score(result, hal)
        for field in ("accuracy", "source_coverage", "retrieval_confidence", "latency", "cost"):
            val = getattr(qs.dimensions, field)
            assert 0.0 <= val <= 1.0, f"{field} = {val}"

    def test_all_profiles_return_different_composites(self):
        import config
        result = run_basic_rag(_Q1)
        hal = check_hallucination(_Q1, result.answer, result.chunks)
        scores = {p: compute_quality_score(result, hal, profile=p).composite for p in config.WEIGHT_PROFILES}
        assert len(set(round(s, 4) for s in scores.values())) > 1
