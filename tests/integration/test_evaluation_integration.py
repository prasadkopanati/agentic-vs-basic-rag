"""Integration tests for the evaluation layer.

Hallucination checker uses mocked LLM (no API calls).
Quality score uses real pipeline result objects.
Marked 'integration'.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

import config
from evaluation.hallucination import (
    ClaimResult,
    HallucinationResult,
    check_hallucination,
)
from evaluation.quality_score import QualityScore, compute_quality_score

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_QUESTION = "What is the net worth ratio to be classified as well-capitalized?"
_GOOD_ANSWER = "A credit union must maintain a net worth ratio of at least 7% to be classified as well-capitalized under NCUA's prompt corrective action framework."
_BAD_ANSWER = "Credit unions must hold at least 10% Tier 1 capital under Basel III. The FDIC requires a minimum 8% leverage ratio for all insured institutions."

_CHUNKS = [
    {
        "chunk_id": "risk-based-capital-faqs_42",
        "source_file": "risk-based-capital-faqs.md",
        "text": "An insured credit union is 'well capitalized' if it has a net worth ratio of not less than 7 percent.",
        "source_url": "",
    },
    {
        "chunk_id": "final-risk-based-capital-rule_10",
        "source_file": "final-risk-based-capital-rule.md",
        "text": "NCUA's prompt corrective action framework establishes net worth categories for federally insured credit unions.",
        "source_url": "",
    },
]


def _llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.usage_metadata = {"input_tokens": 200, "output_tokens": 50}
    return resp


# ---------------------------------------------------------------------------
# Hallucination checker integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCheckHallucinationIntegration:
    def _judge_json(self, claims: list[dict]) -> str:
        return json.dumps(claims)

    def test_fully_sourced_answer_returns_warning_false(self):
        verdict = self._judge_json([
            {"claim": "7% NWR required.", "sourced": True, "evidence_chunk_id": "risk-based-capital-faqs_42"},
        ])
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = _llm_response(verdict)
            result = check_hallucination(_QUESTION, _GOOD_ANSWER, _CHUNKS)

        assert isinstance(result, HallucinationResult)
        assert result.faithfulness_score == pytest.approx(1.0)
        assert result.has_warning is False

    def test_unsourced_claim_sets_warning_true(self):
        verdict = self._judge_json([
            {"claim": "7% NWR required.", "sourced": True, "evidence_chunk_id": "risk-based-capital-faqs_42"},
            {"claim": "Basel III 10% Tier 1 capital.", "sourced": False, "evidence_chunk_id": None},
        ])
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = _llm_response(verdict)
            result = check_hallucination(_QUESTION, _BAD_ANSWER, _CHUNKS)

        assert result.has_warning is True
        assert result.faithfulness_score == pytest.approx(0.5)

    def test_faithfulness_score_equals_sourced_fraction(self):
        verdict = self._judge_json([
            {"claim": "A.", "sourced": True, "evidence_chunk_id": "c0"},
            {"claim": "B.", "sourced": True, "evidence_chunk_id": "c0"},
            {"claim": "C.", "sourced": False, "evidence_chunk_id": None},
            {"claim": "D.", "sourced": False, "evidence_chunk_id": None},
        ])
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = _llm_response(verdict)
            result = check_hallucination(_QUESTION, "some answer", _CHUNKS)

        assert result.faithfulness_score == pytest.approx(0.5)
        assert len(result.claims) == 4

    def test_llm_exception_returns_degraded_result(self):
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.side_effect = RuntimeError("API timeout")
            result = check_hallucination(_QUESTION, _GOOD_ANSWER, _CHUNKS)

        assert result.faithfulness_score is None
        assert result.has_warning is None
        assert result.claims == []

    def test_invalid_json_returns_degraded_result(self):
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = _llm_response("Sorry, I cannot evaluate this.")
            result = check_hallucination(_QUESTION, _GOOD_ANSWER, _CHUNKS)

        assert result.faithfulness_score is None

    def test_llm_called_once(self):
        verdict = self._judge_json([
            {"claim": "7% NWR.", "sourced": True, "evidence_chunk_id": "risk-based-capital-faqs_42"},
        ])
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = _llm_response(verdict)
            check_hallucination(_QUESTION, _GOOD_ANSWER, _CHUNKS)

        instance.invoke.assert_called_once()

    def test_markdown_fenced_json_parsed_correctly(self):
        raw_claims = [{"claim": "7% NWR.", "sourced": True, "evidence_chunk_id": "c0"}]
        verdict = f"```json\n{json.dumps(raw_claims)}\n```"
        with patch("evaluation.hallucination.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = _llm_response(verdict)
            result = check_hallucination(_QUESTION, _GOOD_ANSWER, _CHUNKS)

        assert result.faithfulness_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Quality score integration tests (no LLM needed)
# ---------------------------------------------------------------------------


class _PipelineResult:
    """Minimal duck-typed stand-in for Basic/Agentic RAGResult."""
    def __init__(self, retrieval_confidence, latency_s, input_tokens, output_tokens, chunks=None):
        self.retrieval_confidence = retrieval_confidence
        self.latency_s = latency_s
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.chunks = chunks or []


def _hal(sourced_ids: list[str], unsourced: int) -> HallucinationResult:
    claims = [ClaimResult(f"claim {i}", True, cid) for i, cid in enumerate(sourced_ids)]
    claims += [ClaimResult(f"bad {i}", False, None) for i in range(unsourced)]
    total = len(claims)
    score = len(sourced_ids) / total if total else 1.0
    return HallucinationResult(claims=claims, faithfulness_score=score, has_warning=unsourced > 0)


@pytest.mark.integration
class TestComputeQualityScoreIntegration:
    def test_basic_rag_with_unsourced_claims_low_score(self):
        result = _PipelineResult(
            retrieval_confidence=0.50,
            latency_s=3.0,
            input_tokens=2000,
            output_tokens=100,
            chunks=[{"chunk_id": f"c{i}"} for i in range(4)],
        )
        hal = _hal(sourced_ids=["c0"], unsourced=2)
        qs = compute_quality_score(result, hal, profile="compliance_grade")
        assert qs.composite <= 0.60

    def test_agentic_with_zero_retries_good_answer_high_score(self):
        result = _PipelineResult(
            retrieval_confidence=1.0,   # 0 retries
            latency_s=5.0,
            input_tokens=4000,
            output_tokens=300,
            chunks=[{"chunk_id": f"c{i}"} for i in range(4)],
        )
        hal = _hal(sourced_ids=["c0", "c1", "c2"], unsourced=0)
        qs = compute_quality_score(result, hal, profile="compliance_grade")
        assert qs.composite >= 0.70

    def test_score_gap_between_pipelines(self):
        basic_result = _PipelineResult(0.50, 3.0, 2000, 100, [{"chunk_id": f"c{i}"} for i in range(4)])
        agentic_result = _PipelineResult(1.0, 5.0, 4000, 300, [{"chunk_id": f"c{i}"} for i in range(4)])
        basic_hal = _hal(sourced_ids=["c0"], unsourced=2)
        agentic_hal = _hal(sourced_ids=["c0", "c1", "c2"], unsourced=0)

        basic_qs = compute_quality_score(basic_result, basic_hal)
        agentic_qs = compute_quality_score(agentic_result, agentic_hal)

        assert agentic_qs.composite > basic_qs.composite

    def test_all_profiles_return_quality_score(self):
        result = _PipelineResult(0.7, 3.0, 2000, 100)
        hal = _hal(sourced_ids=["c0", "c1"], unsourced=1)
        for profile in config.WEIGHT_PROFILES:
            qs = compute_quality_score(result, hal, profile=profile)
            assert isinstance(qs, QualityScore)
            assert qs.profile == profile

    def test_dimension_scores_in_unit_interval(self):
        result = _PipelineResult(0.7, 3.0, 2000, 100, [{"chunk_id": "c0"}])
        hal = _hal(sourced_ids=["c0"], unsourced=1)
        qs = compute_quality_score(result, hal)
        for field in ("accuracy", "source_coverage", "retrieval_confidence", "latency", "cost"):
            val = getattr(qs.dimensions, field)
            assert 0.0 <= val <= 1.0, f"{field} = {val} out of [0,1]"
