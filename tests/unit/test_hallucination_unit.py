"""Unit tests for pure-logic helpers in evaluation/hallucination.py.

No I/O, no LLM calls, no network.
"""

import json
import pytest

from evaluation.hallucination import (
    ClaimResult,
    HallucinationResult,
    _parse_judge_response,
    _compute_faithfulness,
)


# ---------------------------------------------------------------------------
# ClaimResult / HallucinationResult dataclasses
# ---------------------------------------------------------------------------


class TestClaimResult:
    def test_fields_accessible(self):
        c = ClaimResult(claim="Net worth must be 7%.", sourced=True, evidence_chunk_id="doc_0")
        assert c.claim == "Net worth must be 7%."
        assert c.sourced is True
        assert c.evidence_chunk_id == "doc_0"

    def test_unsourced_has_none_chunk_id(self):
        c = ClaimResult(claim="Made-up fact.", sourced=False, evidence_chunk_id=None)
        assert c.evidence_chunk_id is None


class TestHallucinationResult:
    def test_fully_sourced(self):
        claims = [ClaimResult("fact A", True, "c0"), ClaimResult("fact B", True, "c1")]
        r = HallucinationResult(claims=claims, faithfulness_score=1.0, has_warning=False)
        assert r.faithfulness_score == pytest.approx(1.0)
        assert r.has_warning is False

    def test_partially_sourced(self):
        claims = [ClaimResult("fact A", True, "c0"), ClaimResult("bad fact", False, None)]
        r = HallucinationResult(claims=claims, faithfulness_score=0.5, has_warning=True)
        assert r.faithfulness_score == pytest.approx(0.5)
        assert r.has_warning is True

    def test_graceful_degradation_fields_are_none(self):
        r = HallucinationResult(claims=[], faithfulness_score=None, has_warning=None)
        assert r.faithfulness_score is None
        assert r.has_warning is None
        assert r.claims == []


# ---------------------------------------------------------------------------
# _compute_faithfulness
# ---------------------------------------------------------------------------


class TestComputeFaithfulness:
    def test_all_sourced(self):
        claims = [ClaimResult("a", True, "c0"), ClaimResult("b", True, "c1")]
        assert _compute_faithfulness(claims) == pytest.approx(1.0)

    def test_none_sourced(self):
        claims = [ClaimResult("a", False, None), ClaimResult("b", False, None)]
        assert _compute_faithfulness(claims) == pytest.approx(0.0)

    def test_half_sourced(self):
        claims = [ClaimResult("a", True, "c0"), ClaimResult("b", False, None)]
        assert _compute_faithfulness(claims) == pytest.approx(0.5)

    def test_empty_claims_returns_one(self):
        # Vacuously clean: no claims to dispute
        assert _compute_faithfulness([]) == pytest.approx(1.0)

    def test_single_unsourced(self):
        claims = [ClaimResult("bad", False, None)]
        assert _compute_faithfulness(claims) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _parse_judge_response
# ---------------------------------------------------------------------------


class TestParseJudgeResponse:
    def _valid_json(self, claims: list[dict]) -> str:
        return json.dumps(claims)

    def test_parses_sourced_claim(self):
        raw = self._valid_json([{"claim": "7% NWR.", "sourced": True, "evidence_chunk_id": "doc_0"}])
        claims = _parse_judge_response(raw)
        assert len(claims) == 1
        assert claims[0].claim == "7% NWR."
        assert claims[0].sourced is True
        assert claims[0].evidence_chunk_id == "doc_0"

    def test_parses_unsourced_claim(self):
        raw = self._valid_json([{"claim": "Made up.", "sourced": False, "evidence_chunk_id": None}])
        claims = _parse_judge_response(raw)
        assert claims[0].sourced is False
        assert claims[0].evidence_chunk_id is None

    def test_parses_multiple_claims(self):
        raw = self._valid_json([
            {"claim": "A.", "sourced": True, "evidence_chunk_id": "c0"},
            {"claim": "B.", "sourced": False, "evidence_chunk_id": None},
            {"claim": "C.", "sourced": True, "evidence_chunk_id": "c1"},
        ])
        claims = _parse_judge_response(raw)
        assert len(claims) == 3

    def test_strips_markdown_fences(self):
        raw = '```json\n[{"claim": "X.", "sourced": true, "evidence_chunk_id": "c0"}]\n```'
        claims = _parse_judge_response(raw)
        assert len(claims) == 1
        assert claims[0].claim == "X."

    def test_strips_plain_code_fence(self):
        raw = '```\n[{"claim": "X.", "sourced": true, "evidence_chunk_id": null}]\n```'
        claims = _parse_judge_response(raw)
        assert len(claims) == 1

    def test_invalid_json_returns_empty_list(self):
        claims = _parse_judge_response("not json at all")
        assert claims == []

    def test_empty_array_returns_empty_list(self):
        claims = _parse_judge_response("[]")
        assert claims == []

    def test_missing_evidence_chunk_id_defaults_to_none(self):
        raw = self._valid_json([{"claim": "X.", "sourced": True}])
        claims = _parse_judge_response(raw)
        assert claims[0].evidence_chunk_id is None

    def test_missing_sourced_defaults_to_false(self):
        raw = self._valid_json([{"claim": "X.", "evidence_chunk_id": None}])
        claims = _parse_judge_response(raw)
        assert claims[0].sourced is False
