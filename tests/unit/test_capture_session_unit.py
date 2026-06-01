"""Unit tests for pure-logic helpers in scripts/capture_session.py.

No I/O, no network, no LLM calls. Pure function coverage only.
"""

from __future__ import annotations

import pytest

from evaluation.hallucination import ClaimResult, HallucinationResult
from evaluation.quality_score import DimensionScores, QualityScore
from pipelines.agentic_rag import AgenticRAGResult
from pipelines.basic_rag import BasicRAGResult
from scripts.capture_session import (
    hallucination_to_dict,
    make_dry_run_entry,
    parse_query_ids,
    result_fields,
    score_to_dict,
)


# ---------------------------------------------------------------------------
# parse_query_ids
# ---------------------------------------------------------------------------


class TestParseQueryIds:
    def test_none_returns_all_indices(self):
        assert parse_query_ids(None, 10) == list(range(10))

    def test_empty_string_returns_all_indices(self):
        assert parse_query_ids("", 10) == list(range(10))

    def test_single_id(self):
        assert parse_query_ids("Q1", 10) == [0]

    def test_single_id_last(self):
        assert parse_query_ids("Q10", 10) == [9]

    def test_multiple_ids_ordered(self):
        assert parse_query_ids("Q1,Q3,Q9", 10) == [0, 2, 8]

    def test_whitespace_around_ids(self):
        assert parse_query_ids("Q1, Q3, Q5", 10) == [0, 2, 4]

    def test_lowercase_q_accepted(self):
        assert parse_query_ids("q2,q4", 10) == [1, 3]

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid query ID"):
            parse_query_ids("X1", 10)

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_query_ids("Q11", 10)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            parse_query_ids("Q0", 10)


# ---------------------------------------------------------------------------
# result_fields (duck-typed on BasicRAGResult and AgenticRAGResult)
# ---------------------------------------------------------------------------


class TestResultFields:
    def _basic(self, **overrides):
        defaults = dict(
            query="q",
            answer="ans",
            chunks=[{"chunk_id": "c1"}],
            latency_s=1.5,
            input_tokens=100,
            output_tokens=50,
            retrieval_confidence=0.75,
        )
        return BasicRAGResult(**{**defaults, **overrides})

    def _agentic(self, **overrides):
        defaults = dict(
            query="q",
            answer="ans",
            chunks=[{"chunk_id": "c1"}],
            step_log=[],
            retry_count=2,
            retrieval_confidence=0.6,
            latency_s=3.0,
            input_tokens=400,
            output_tokens=120,
            grader_scores=[0.3, 0.7],
            best_grader_score=0.7,
        )
        return AgenticRAGResult(**{**defaults, **overrides})

    def test_basic_result_has_required_keys(self):
        fields = result_fields(self._basic())
        required = {"answer", "chunks", "latency_s", "input_tokens",
                    "output_tokens", "retrieval_confidence", "retry_count", "grader_scores"}
        assert required <= set(fields.keys())

    def test_basic_result_retry_count_is_zero(self):
        assert result_fields(self._basic())["retry_count"] == 0

    def test_basic_result_grader_scores_is_empty_list(self):
        assert result_fields(self._basic())["grader_scores"] == []

    def test_agentic_result_retry_count_preserved(self):
        assert result_fields(self._agentic(retry_count=3))["retry_count"] == 3

    def test_agentic_result_grader_scores_preserved(self):
        scores = [0.2, 0.5, 0.9]
        assert result_fields(self._agentic(grader_scores=scores))["grader_scores"] == scores

    def test_answer_value_preserved(self):
        assert result_fields(self._basic(answer="hello"))["answer"] == "hello"

    def test_latency_value_preserved(self):
        assert result_fields(self._basic(latency_s=4.2))["latency_s"] == pytest.approx(4.2)


# ---------------------------------------------------------------------------
# score_to_dict
# ---------------------------------------------------------------------------


class TestScoreToDict:
    def _score(self, composite=0.82, profile="compliance_grade"):
        dims = DimensionScores(
            accuracy=0.9,
            source_coverage=0.8,
            retrieval_confidence=0.7,
            latency=0.6,
            cost=0.5,
        )
        return QualityScore(composite=composite, dimensions=dims, profile=profile)

    def test_composite_preserved(self):
        assert score_to_dict(self._score(composite=0.75))["composite"] == pytest.approx(0.75)

    def test_profile_preserved(self):
        assert score_to_dict(self._score(profile="high_throughput"))["profile"] == "high_throughput"

    def test_dimensions_is_dict_with_five_keys(self):
        dims = score_to_dict(self._score())["dimensions"]
        assert set(dims.keys()) == {
            "accuracy", "source_coverage", "retrieval_confidence", "latency", "cost"
        }

    def test_dimension_values_preserved(self):
        dims = score_to_dict(self._score())["dimensions"]
        assert dims["accuracy"] == pytest.approx(0.9)
        assert dims["latency"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# hallucination_to_dict
# ---------------------------------------------------------------------------


class TestHallucinationToDict:
    def _hall(self, sourced=True, warning=False, score=1.0):
        claim = ClaimResult(
            claim="The ratio is 7%.",
            sourced=sourced,
            evidence_chunk_id="doc_0" if sourced else None,
        )
        return HallucinationResult(
            claims=[claim],
            faithfulness_score=score,
            has_warning=warning,
        )

    def test_faithfulness_score_preserved(self):
        d = hallucination_to_dict(self._hall(score=0.5))
        assert d["faithfulness_score"] == pytest.approx(0.5)

    def test_has_warning_preserved(self):
        assert hallucination_to_dict(self._hall(warning=True))["has_warning"] is True

    def test_claims_list_length(self):
        assert len(hallucination_to_dict(self._hall())["claims"]) == 1

    def test_claim_fields_present(self):
        claim = hallucination_to_dict(self._hall())["claims"][0]
        assert set(claim.keys()) == {"claim", "sourced", "evidence_chunk_id"}

    def test_unsourced_claim_evidence_is_none(self):
        d = hallucination_to_dict(self._hall(sourced=False))
        assert d["claims"][0]["evidence_chunk_id"] is None

    def test_faithfulness_score_none_preserved(self):
        h = HallucinationResult(claims=[], faithfulness_score=None, has_warning=None)
        assert hallucination_to_dict(h)["faithfulness_score"] is None


# ---------------------------------------------------------------------------
# make_dry_run_entry
# ---------------------------------------------------------------------------


class TestMakeDryRunEntry:
    def _entry(self):
        return make_dry_run_entry("Q3", "What triggers a SAR filing?")

    def test_query_id_preserved(self):
        assert self._entry()["query_id"] == "Q3"

    def test_query_text_preserved(self):
        assert self._entry()["query_text"] == "What triggers a SAR filing?"

    def test_has_required_top_level_keys(self):
        keys = self._entry().keys()
        required = {
            "query_id", "query_text",
            "basic", "agentic",
            "basic_score", "agentic_score",
            "basic_hallucination", "agentic_hallucination",
        }
        assert required <= set(keys)

    def test_basic_answer_is_dry_run_placeholder(self):
        assert "dry-run" in self._entry()["basic"]["answer"]

    def test_numeric_fields_are_zero(self):
        basic = self._entry()["basic"]
        assert basic["latency_s"] == 0.0
        assert basic["input_tokens"] == 0
        assert basic["retrieval_confidence"] == 0.0

    def test_basic_retry_count_is_zero(self):
        assert self._entry()["basic"]["retry_count"] == 0

    def test_score_composite_is_zero(self):
        assert self._entry()["basic_score"]["composite"] == 0.0

    def test_score_has_five_dimensions(self):
        dims = self._entry()["basic_score"]["dimensions"]
        assert len(dims) == 5

    def test_hallucination_faithfulness_is_none(self):
        assert self._entry()["basic_hallucination"]["faithfulness_score"] is None

    def test_agentic_and_basic_are_independent_dicts(self):
        entry = self._entry()
        # Mutating agentic should not affect basic
        entry["agentic"]["answer"] = "modified"
        assert entry["basic"]["answer"] != "modified"
