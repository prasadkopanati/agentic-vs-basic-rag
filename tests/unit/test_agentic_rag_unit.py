"""Unit tests for pure-logic helpers in the agentic_rag pipeline.

No I/O, no network, no external services.
"""

import pytest

import config
from pipelines.agentic_rag import (
    AgenticRAGResult,
    _compute_retrieval_confidence,
    _get_manifest_vocabulary,
    _parse_grader_response,
    _route,
)


# ---------------------------------------------------------------------------
# _compute_retrieval_confidence
# ---------------------------------------------------------------------------


class TestComputeRetrievalConfidence:
    def test_zero_retries_returns_one(self):
        assert _compute_retrieval_confidence(0, max_retries=2) == pytest.approx(1.0)

    def test_one_retry_returns_half(self):
        assert _compute_retrieval_confidence(1, max_retries=2) == pytest.approx(0.5)

    def test_at_max_retries_returns_zero(self):
        assert _compute_retrieval_confidence(2, max_retries=2) == pytest.approx(0.0)

    def test_zero_max_retries_returns_one(self):
        # Degenerate case: no retries possible → always 1.0
        assert _compute_retrieval_confidence(0, max_retries=0) == pytest.approx(1.0)

    def test_uses_config_max_retries_by_default(self):
        result = _compute_retrieval_confidence(config.MAX_RETRIES)
        assert result == pytest.approx(0.0)

    def test_result_clamped_at_zero(self):
        # retry_count > max_retries should not go negative
        result = _compute_retrieval_confidence(5, max_retries=2)
        assert result >= 0.0

    def test_result_in_unit_interval(self):
        for retries in range(config.MAX_RETRIES + 1):
            r = _compute_retrieval_confidence(retries)
            assert 0.0 <= r <= 1.0


# ---------------------------------------------------------------------------
# _parse_grader_response — returns (bool, str, float)
# ---------------------------------------------------------------------------


class TestParseGraderResponse:
    # --- JSON format (primary path) ---

    def test_json_yes_returns_true_score_one(self):
        result, feedback, score = _parse_grader_response(
            '{"grading_result": "yes", "feedback": "", "grading_score": 1.0}'
        )
        assert result is True
        assert feedback == ""
        assert score == pytest.approx(1.0)

    def test_json_no_returns_false_with_feedback_and_score(self):
        result, feedback, score = _parse_grader_response(
            '{"grading_result": "no", "feedback": "Missing NEV threshold.", "grading_score": 0.60}'
        )
        assert result is False
        assert "NEV" in feedback
        assert score == pytest.approx(0.60)

    def test_json_yes_case_insensitive(self):
        result, _, score = _parse_grader_response(
            '{"grading_result": "YES", "feedback": "", "grading_score": 1.0}'
        )
        assert result is True
        assert score == pytest.approx(1.0)

    def test_json_score_clamped_above_one(self):
        _, _, score = _parse_grader_response(
            '{"grading_result": "no", "feedback": "x", "grading_score": 1.5}'
        )
        assert score == pytest.approx(1.0)

    def test_json_score_clamped_below_zero(self):
        _, _, score = _parse_grader_response(
            '{"grading_result": "no", "feedback": "x", "grading_score": -0.3}'
        )
        assert score == pytest.approx(0.0)

    def test_json_with_preamble_still_parsed(self):
        # Model adds text before the JSON object despite instructions
        text = 'Here is my assessment:\n{"grading_result": "yes", "feedback": "", "grading_score": 1.0}'
        result, _, score = _parse_grader_response(text)
        assert result is True
        assert score == pytest.approx(1.0)

    def test_json_no_with_zero_score(self):
        result, feedback, score = _parse_grader_response(
            '{"grading_result": "no", "feedback": "PCA tier not addressed.", "grading_score": 0.0}'
        )
        assert result is False
        assert score == pytest.approx(0.0)
        assert "PCA" in feedback

    def test_malformed_json_falls_back_to_text_parser(self):
        # Malformed JSON → fallback parser → legacy YES
        result, feedback, score = _parse_grader_response("YES")
        assert result is True
        assert score == pytest.approx(1.0)

    def test_malformed_json_no_falls_back(self):
        result, feedback, score = _parse_grader_response(
            "NO. Missing: The documents do not address the SAR deadline."
        )
        assert result is False
        assert "SAR" in feedback
        assert score == pytest.approx(0.0)  # unknown in fallback

    # --- Legacy text fallback ---

    def test_fallback_yes_returns_true(self):
        result, _, score = _parse_grader_response("YES")
        assert result is True
        assert score == pytest.approx(1.0)

    def test_fallback_no_returns_false(self):
        result, _, score = _parse_grader_response("NO")
        assert result is False
        assert score == pytest.approx(0.0)

    def test_fallback_lowercase_yes(self):
        result, _, _ = _parse_grader_response("yes")
        assert result is True

    def test_fallback_lowercase_no(self):
        result, _, _ = _parse_grader_response("no")
        assert result is False

    def test_fallback_yes_with_explanation(self):
        result, _, _ = _parse_grader_response("Yes, the documents contain sufficient information.")
        assert result is True

    def test_fallback_no_with_explanation(self):
        result, _, _ = _parse_grader_response("No, the documents do not address the question.")
        assert result is False

    def test_fallback_missing_colon_extracts_feedback(self):
        result, feedback, _ = _parse_grader_response(
            "NO. Missing: The SAR filing deadline is not stated."
        )
        assert result is False
        assert "SAR filing deadline" in feedback

    def test_fallback_leading_whitespace_stripped(self):
        result, _, _ = _parse_grader_response("  YES")
        assert result is True

    def test_fallback_empty_string_returns_false(self):
        result, feedback, score = _parse_grader_response("")
        assert result is False
        assert feedback == ""
        assert score == pytest.approx(0.0)

    def test_fallback_unrecognized_returns_false(self):
        result, _, _ = _parse_grader_response("MAYBE")
        assert result is False

    def test_fallback_revised_assessment_yes(self):
        text = "After reviewing the documents, Revised assessment: YES"
        result, _, score = _parse_grader_response(text)
        assert result is True
        assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _route
# ---------------------------------------------------------------------------


class TestRoute:
    def _state(
        self,
        grader_relevant: bool,
        retry_count: int,
        consecutive_stable_retries: int = 0,
        best_grader_score: float = 0.0,
    ) -> dict:
        return {
            "grader_relevant": grader_relevant,
            "retry_count": retry_count,
            "consecutive_stable_retries": consecutive_stable_retries,
            "best_grader_score": best_grader_score,
        }

    def test_relevant_routes_to_generator(self):
        assert _route(self._state(True, 0)) == "generator"

    def test_not_relevant_under_budget_routes_to_retry(self):
        assert _route(self._state(False, 0)) == "retry_counter"

    def test_not_relevant_at_max_retries_routes_to_generator(self):
        assert _route(self._state(False, config.MAX_RETRIES)) == "generator"

    def test_relevant_and_at_budget_routes_to_generator(self):
        assert _route(self._state(True, config.MAX_RETRIES)) == "generator"

    def test_not_relevant_one_before_max_routes_to_retry(self):
        assert _route(self._state(False, config.MAX_RETRIES - 1)) == "retry_counter"

    # --- Plateau-aware early exit ---

    def test_plateau_exit_triggers_at_stable_2_with_sufficient_score(self):
        assert _route(self._state(False, 3, consecutive_stable_retries=2, best_grader_score=0.67)) == "generator"

    def test_plateau_exit_requires_stable_at_least_2(self):
        # stable=1 is not enough — still retry
        assert _route(self._state(False, 3, consecutive_stable_retries=1, best_grader_score=0.67)) == "retry_counter"

    def test_plateau_exit_requires_score_at_least_50_pct(self):
        # stable=2 but score below floor — no early exit (not enough meaningful coverage)
        assert _route(self._state(False, 3, consecutive_stable_retries=2, best_grader_score=0.33)) == "retry_counter"

    def test_plateau_exit_does_not_override_budget_exhaustion(self):
        # At max retries, budget exit takes precedence regardless of plateau state
        assert _route(self._state(False, config.MAX_RETRIES, consecutive_stable_retries=0, best_grader_score=0.0)) == "generator"

    def test_plateau_exit_at_exactly_50_pct_floor(self):
        assert _route(self._state(False, 2, consecutive_stable_retries=2, best_grader_score=0.50)) == "generator"


# ---------------------------------------------------------------------------
# AgenticRAGResult dataclass
# ---------------------------------------------------------------------------


class TestAgenticRAGResult:
    def test_all_fields_accessible(self):
        step = [{"node": "rewriter", "status": "done", "detail": "rewrote"}]
        r = AgenticRAGResult(
            query="test query",
            answer="test answer",
            chunks=[],
            step_log=step,
            retry_count=1,
            retrieval_confidence=0.5,
            latency_s=2.0,
            input_tokens=500,
            output_tokens=100,
            grader_scores=[0.4, 0.8, 1.0],
        )
        assert r.query == "test query"
        assert r.answer == "test answer"
        assert r.retry_count == 1
        assert r.retrieval_confidence == pytest.approx(0.5)
        assert r.latency_s == pytest.approx(2.0)
        assert r.input_tokens == 500
        assert r.output_tokens == 100
        assert r.grader_scores == [0.4, 0.8, 1.0]

    def test_grader_scores_defaults_to_empty_list(self):
        r = AgenticRAGResult("q", "a", [], [], 0, 1.0, 1.0, 100, 50)
        assert r.grader_scores == []

    def test_step_log_preserved(self):
        steps = [
            {"node": "rewriter", "status": "done", "detail": "rewrote"},
            {"node": "retriever", "status": "done", "detail": "retrieved 4"},
        ]
        r = AgenticRAGResult("q", "a", [], steps, 0, 1.0, 1.0, 100, 50)
        assert len(r.step_log) == 2
        assert r.step_log[0]["node"] == "rewriter"

    def test_retrieval_confidence_consistent_with_retry_count(self):
        # 0 retries → confidence 1.0; 1 retry → 0.5 (with MAX_RETRIES=2)
        r0 = AgenticRAGResult("q", "a", [], [], 0, _compute_retrieval_confidence(0), 1.0, 0, 0)
        r1 = AgenticRAGResult("q", "a", [], [], 1, _compute_retrieval_confidence(1), 1.0, 0, 0)
        assert r0.retrieval_confidence > r1.retrieval_confidence


# ---------------------------------------------------------------------------
# _get_manifest_vocabulary
# ---------------------------------------------------------------------------


_SAMPLE_MANIFEST = {
    "sar-doc.md": {
        "topics": ["BSA", "SAR"],
        "thresholds": ["$5,000 criminal violations suspect identified", "$25,000 no suspect"],
        "citations": ["748.1(d)(1)", "1010.311"],
        "timeframes": ["30 days", "60 days"],
        "key_terms": ["suspicious activity report", "SAR", "BSA E-Filing", "FinCEN"],
    },
    "irr-doc.md": {
        "topics": ["IRR"],
        "thresholds": ["post-shock NEV below 4 percent High risk"],
        "citations": ["12 CFR 741.3"],
        "timeframes": [],
        "key_terms": ["interest rate risk", "NEV", "net economic value"],
    },
}


class TestGetManifestVocabulary:
    def test_returns_empty_string_for_empty_manifest(self):
        result = _get_manifest_vocabulary("SAR threshold missing", manifest={})
        assert result == ""

    def test_matches_sar_key_terms_in_feedback(self):
        result = _get_manifest_vocabulary(
            "minimum dollar amount for SAR filing when suspect identified",
            manifest=_SAMPLE_MANIFEST,
        )
        assert "$5,000 criminal violations suspect identified" in result
        assert "748.1(d)(1)" in result

    def test_matches_irr_key_terms_in_feedback(self):
        result = _get_manifest_vocabulary(
            "NEV ratio threshold for High risk classification",
            manifest=_SAMPLE_MANIFEST,
        )
        assert "post-shock NEV below 4 percent" in result

    def test_does_not_cross_contaminate_unrelated_domains(self):
        result = _get_manifest_vocabulary(
            "interest rate risk NEV threshold",
            manifest=_SAMPLE_MANIFEST,
        )
        # IRR doc should dominate; SAR-specific threshold should not dominate
        assert "post-shock NEV below 4 percent High risk" in result

    def test_result_respects_max_chars(self):
        result = _get_manifest_vocabulary("SAR", manifest=_SAMPLE_MANIFEST, max_chars=20)
        assert len(result) <= 20

    def test_unmatched_feedback_returns_empty(self):
        result = _get_manifest_vocabulary(
            "completely unrelated topic with no matching terms",
            manifest=_SAMPLE_MANIFEST,
        )
        assert result == ""
