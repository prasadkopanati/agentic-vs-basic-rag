"""Unit tests for pure-logic helpers in evaluation/quality_score.py.

No I/O, no LLM calls, no network.
"""

import pytest

import config
from evaluation.hallucination import ClaimResult, HallucinationResult
from evaluation.quality_score import (
    DimensionScores,
    QualityScore,
    _compute_cost_score,
    _compute_latency_score,
    _compute_source_coverage,
    _compute_composite,
    compute_quality_score,
)


# ---------------------------------------------------------------------------
# DimensionScores / QualityScore dataclasses
# ---------------------------------------------------------------------------


class TestDimensionScores:
    def test_all_fields_accessible(self):
        d = DimensionScores(
            accuracy=0.8,
            source_coverage=0.75,
            retrieval_confidence=0.9,
            latency=0.7,
            cost=0.95,
        )
        assert d.accuracy == pytest.approx(0.8)
        assert d.source_coverage == pytest.approx(0.75)
        assert d.retrieval_confidence == pytest.approx(0.9)
        assert d.latency == pytest.approx(0.7)
        assert d.cost == pytest.approx(0.95)


class TestQualityScore:
    def test_all_fields_accessible(self):
        dims = DimensionScores(0.8, 0.75, 0.9, 0.7, 0.95)
        qs = QualityScore(composite=0.82, dimensions=dims, profile="compliance_grade")
        assert qs.composite == pytest.approx(0.82)
        assert qs.profile == "compliance_grade"


# ---------------------------------------------------------------------------
# _compute_latency_score
# ---------------------------------------------------------------------------


class TestComputeLatencyScore:
    def test_zero_latency_returns_one(self):
        assert _compute_latency_score(0.0) == pytest.approx(1.0)

    def test_at_ceiling_returns_zero(self):
        assert _compute_latency_score(config.LATENCY_CEILING) == pytest.approx(0.0)

    def test_half_ceiling(self):
        assert _compute_latency_score(config.LATENCY_CEILING / 2) == pytest.approx(0.5)

    def test_over_ceiling_clamped_to_zero(self):
        assert _compute_latency_score(config.LATENCY_CEILING * 2) == pytest.approx(0.0)

    def test_result_in_unit_interval(self):
        for t in [0.0, 1.0, 5.0, 10.0, 15.0]:
            score = _compute_latency_score(t)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _compute_cost_score
# ---------------------------------------------------------------------------


class TestComputeCostScore:
    def test_zero_tokens_returns_one(self):
        assert _compute_cost_score(0, 0) == pytest.approx(1.0)

    def test_result_in_unit_interval(self):
        # Any token counts should stay in [0,1]
        for in_tok, out_tok in [(100, 50), (10000, 5000), (1_000_000, 500_000)]:
            score = _compute_cost_score(in_tok, out_tok)
            assert 0.0 <= score <= 1.0

    def test_very_expensive_clamped_to_zero(self):
        # 1M input + 500K output at Sonnet pricing is well over the $0.10 ceiling
        assert _compute_cost_score(1_000_000, 500_000) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _compute_source_coverage
# ---------------------------------------------------------------------------


class TestComputeSourceCoverage:
    def _claim(self, sourced: bool, chunk_id: str | None = None) -> ClaimResult:
        return ClaimResult(claim="test", sourced=sourced, evidence_chunk_id=chunk_id)

    def _chunk(self, chunk_id: str, source_file: str) -> dict:
        return {"chunk_id": chunk_id, "source_file": source_file}

    def _chunk_p(self, chunk_id: str, source_file: str, retrieval_pass: int) -> dict:
        return {"chunk_id": chunk_id, "source_file": source_file, "retrieval_pass": retrieval_pass}

    def test_all_docs_cited(self):
        claims = [self._claim(True, "doc_a.md_0"), self._claim(True, "doc_b.md_0")]
        chunks = [self._chunk("doc_a.md_0", "doc_a.md"), self._chunk("doc_b.md_0", "doc_b.md")]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(1.0)

    def test_no_claims_returns_zero(self):
        chunks = [self._chunk(f"f{i}.md_0", f"f{i}.md") for i in range(4)]
        assert _compute_source_coverage([], chunks) == pytest.approx(0.0)

    def test_zero_chunks_returns_zero(self):
        claims = [self._claim(True, "doc_a.md_0")]
        assert _compute_source_coverage(claims, []) == pytest.approx(0.0)

    def test_one_of_four_docs_cited(self):
        claims = [self._claim(True, "f0.md_0"), self._claim(False, None)]
        chunks = [self._chunk(f"f{i}.md_0", f"f{i}.md") for i in range(4)]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(0.25)

    def test_duplicate_citations_count_once(self):
        # Both claims cite the same chunk — still just one doc cited out of four
        claims = [self._claim(True, "f0.md_0"), self._claim(True, "f0.md_0")]
        chunks = [self._chunk(f"f{i}.md_0", f"f{i}.md") for i in range(4)]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(0.25)

    def test_unsourced_claims_do_not_count(self):
        claims = [self._claim(False, "f0.md_0")]  # sourced=False even with chunk id
        chunks = [self._chunk(f"f{i}.md_0", f"f{i}.md") for i in range(4)]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(0.0)

    def test_multiple_chunks_same_doc_count_as_one(self):
        # 3 chunks from doc_a, 1 from doc_b → 2 unique docs; both cited → 1.0
        claims = [self._claim(True, "doc_a.md_0"), self._claim(True, "doc_b.md_0")]
        chunks = [
            self._chunk("doc_a.md_0", "doc_a.md"),
            self._chunk("doc_a.md_1", "doc_a.md"),
            self._chunk("doc_a.md_2", "doc_a.md"),
            self._chunk("doc_b.md_0", "doc_b.md"),
        ]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(1.0)

    def test_iterative_pipeline_fairness(self):
        # 9 chunks from 3 docs (3 chunks each), generator cites all 3 → 1.0, not 3/9
        docs = ["irr.md", "commloan.md", "bsa.md"]
        chunks = [self._chunk(f"{d}_{i}", d) for d in docs for i in range(3)]
        claims = [self._claim(True, f"{d}_0") for d in docs]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(1.0)

    def test_iterative_pipeline_partial_coverage(self):
        # 9 chunks from 3 docs, but generator only cites 1 of the 3 docs → 0.33
        # (no retrieval_pass metadata → single-shot path, denominator = all 3 docs)
        docs = ["irr.md", "commloan.md", "bsa.md"]
        chunks = [self._chunk(f"{d}_{i}", d) for d in docs for i in range(3)]
        claims = [self._claim(True, "irr.md_0")]  # only irr.md cited
        assert _compute_source_coverage(claims, chunks) == pytest.approx(1 / 3)

    # ------------------------------------------------------------------
    # Pass-scoped denominator (iterative agentic pipeline)
    # ------------------------------------------------------------------

    def test_pass_scoped_single_pass_unchanged(self):
        # All chunks from pass 0 — behaves identically to no retrieval_pass
        chunks = [self._chunk_p(f"f{i}.md_0", f"f{i}.md", 0) for i in range(3)]
        claims = [self._claim(True, "f0.md_0")]
        # denominator = cited ∪ final_pass = {f0} ∪ {f0,f1,f2} = 3; cited = 1 → 0.33
        assert _compute_source_coverage(claims, chunks) == pytest.approx(1 / 3)

    def test_pass_scoped_exploratory_docs_excluded(self):
        # 3-pass retrieval: pass 0 = irr.md, pass 1 = bsa.md, pass 2 = commloan.md (final)
        # Generator cites one doc from each earlier pass plus the final pass doc.
        # Exploratory-only docs from passes 0 and 1 are excluded from denominator.
        chunks = [
            self._chunk_p("irr.md_0", "irr.md", 0),
            self._chunk_p("irr2.md_0", "irr2.md", 0),      # exploratory, not cited
            self._chunk_p("bsa.md_0", "bsa.md", 1),
            self._chunk_p("bsa2.md_0", "bsa2.md", 1),      # exploratory, not cited
            self._chunk_p("commloan.md_0", "commloan.md", 2),
            self._chunk_p("noise.md_0", "noise.md", 2),    # final pass, not cited
        ]
        claims = [
            self._claim(True, "irr.md_0"),
            self._claim(True, "bsa.md_0"),
            self._claim(True, "commloan.md_0"),
        ]
        # denominator = cited {irr,bsa,commloan} ∪ final_pass {commloan,noise} = 4 docs
        # numerator = 3 cited → 3/4 = 0.75
        assert _compute_source_coverage(claims, chunks) == pytest.approx(3 / 4)

    def test_pass_scoped_all_final_pass_cited(self):
        # If all final-pass docs are cited, denominator shrinks to cited-only → 1.0
        chunks = [
            self._chunk_p("old.md_0", "old.md", 0),          # exploratory, not cited
            self._chunk_p("commloan.md_0", "commloan.md", 1),
            self._chunk_p("bsa.md_0", "bsa.md", 1),
        ]
        claims = [
            self._claim(True, "commloan.md_0"),
            self._claim(True, "bsa.md_0"),
        ]
        # denominator = cited {commloan,bsa} ∪ final_pass {commloan,bsa} = 2 → 1.0
        assert _compute_source_coverage(claims, chunks) == pytest.approx(1.0)

    def test_pass_scoped_no_citations(self):
        # No cited docs → numerator=0, denominator=final_pass_docs > 0 → 0.0
        chunks = [
            self._chunk_p("irr.md_0", "irr.md", 0),
            self._chunk_p("bsa.md_0", "bsa.md", 1),
        ]
        claims = [self._claim(False, "irr.md_0")]
        assert _compute_source_coverage(claims, chunks) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _compute_composite
# ---------------------------------------------------------------------------


class TestComputeComposite:
    def test_all_ones_returns_one(self):
        dims = DimensionScores(1.0, 1.0, 1.0, 1.0, 1.0)
        weights = config.WEIGHT_PROFILES["compliance_grade"]
        assert _compute_composite(dims, weights) == pytest.approx(1.0)

    def test_all_zeros_returns_zero(self):
        dims = DimensionScores(0.0, 0.0, 0.0, 0.0, 0.0)
        weights = config.WEIGHT_PROFILES["compliance_grade"]
        assert _compute_composite(dims, weights) == pytest.approx(0.0)

    def test_weights_sum_to_one_for_all_profiles(self):
        for name, weights in config.WEIGHT_PROFILES.items():
            total = sum(weights.values())
            assert total == pytest.approx(1.0), f"Profile {name!r} weights sum to {total}"

    def test_different_profiles_give_different_composites(self):
        dims = DimensionScores(accuracy=1.0, source_coverage=1.0, retrieval_confidence=0.0, latency=0.0, cost=0.0)
        scores = {
            name: _compute_composite(dims, config.WEIGHT_PROFILES[name])
            for name in config.WEIGHT_PROFILES
        }
        # compliance_grade weights accuracy heavily → highest score
        assert scores["compliance_grade"] > scores["cost_optimized"]


# ---------------------------------------------------------------------------
# compute_quality_score — integration with mock result objects
# ---------------------------------------------------------------------------


class _FakeResult:
    """Duck-typed stand-in for BasicRAGResult (no grader_scores attribute)."""
    def __init__(self, retrieval_confidence=0.7, latency_s=3.0, input_tokens=500, output_tokens=100, chunks=None):
        self.retrieval_confidence = retrieval_confidence
        self.latency_s = latency_s
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.chunks = chunks or []


class _FakeAgenticResult(_FakeResult):
    """Duck-typed stand-in for AgenticRAGResult (has grader_scores + best_grader_score)."""
    def __init__(self, *args, grader_scores=None, best_grader_score=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.grader_scores = grader_scores if grader_scores is not None else []
        self.best_grader_score = best_grader_score


class TestComputeQualityScore:
    def _hal(self, sourced: int, unsourced: int, chunk_ids: list[str | None] | None = None) -> HallucinationResult:
        """Build a HallucinationResult with sourced and unsourced claims."""
        if chunk_ids is None:
            chunk_ids = [f"c{i}" for i in range(sourced)] + [None] * unsourced
        total = sourced + unsourced
        claims = []
        for i in range(sourced):
            claims.append(ClaimResult(f"claim {i}", True, chunk_ids[i]))
        for i in range(unsourced):
            claims.append(ClaimResult(f"bad claim {i}", False, None))
        score = sourced / total if total > 0 else 1.0
        return HallucinationResult(claims=claims, faithfulness_score=score, has_warning=unsourced > 0)

    def test_returns_quality_score(self):
        result = _FakeResult()
        hal = self._hal(sourced=3, unsourced=0)
        qs = compute_quality_score(result, hal)
        assert isinstance(qs, QualityScore)

    def test_composite_in_unit_interval(self):
        result = _FakeResult()
        hal = self._hal(sourced=2, unsourced=1)
        qs = compute_quality_score(result, hal)
        assert 0.0 <= qs.composite <= 1.0

    def test_profile_recorded(self):
        result = _FakeResult()
        hal = self._hal(sourced=3, unsourced=0)
        qs = compute_quality_score(result, hal, profile="high_throughput")
        assert qs.profile == "high_throughput"

    def test_perfect_answer_near_one(self):
        # chunks need source_file so document-level coverage calculation works
        fake_chunks = [{"chunk_id": f"c{i}", "source_file": f"doc{i}.md"} for i in range(3)]
        result = _FakeResult(retrieval_confidence=1.0, latency_s=1.0, input_tokens=100, output_tokens=50, chunks=fake_chunks)
        hal = self._hal(sourced=3, unsourced=0, chunk_ids=["c0", "c1", "c2"])
        qs = compute_quality_score(result, hal)
        assert qs.composite > 0.85

    def test_bad_answer_lower_score_than_good(self):
        good_result = _FakeResult(retrieval_confidence=1.0, latency_s=1.0, input_tokens=100, output_tokens=50)
        bad_result = _FakeResult(retrieval_confidence=0.3, latency_s=9.0, input_tokens=5000, output_tokens=500)
        good_hal = self._hal(sourced=3, unsourced=0, chunk_ids=["c0", "c1", "c2"])
        bad_hal = self._hal(sourced=1, unsourced=3)

        good_qs = compute_quality_score(good_result, good_hal)
        bad_qs = compute_quality_score(bad_result, bad_hal)
        assert good_qs.composite > bad_qs.composite

    def test_graceful_degradation_hal_uses_neutral_accuracy(self):
        result = _FakeResult()
        degraded_hal = HallucinationResult(claims=[], faithfulness_score=None, has_warning=None)
        qs = compute_quality_score(result, degraded_hal)
        # Should not raise; composite should be in [0,1]
        assert 0.0 <= qs.composite <= 1.0

    def test_all_three_profiles_produce_different_composites(self):
        result = _FakeResult(retrieval_confidence=0.6, latency_s=2.0, input_tokens=1000, output_tokens=200)
        hal = self._hal(sourced=2, unsourced=1)
        scores = {p: compute_quality_score(result, hal, profile=p).composite for p in config.WEIGHT_PROFILES}
        # All three must differ (different weight emphasis)
        assert len(set(round(s, 6) for s in scores.values())) == 3

    def test_agentic_uses_best_grader_score_as_accuracy(self):
        # Agentic result with grader_scores present → accuracy = best_grader_score, not faithfulness
        result = _FakeAgenticResult(
            retrieval_confidence=0.8,
            grader_scores=[0.67, 1.0],
            best_grader_score=1.0,
        )
        hal = self._hal(sourced=5, unsourced=1)  # faithfulness = 5/6 ≈ 0.833
        qs = compute_quality_score(result, hal)
        assert qs.dimensions.accuracy == pytest.approx(1.0)

    def test_agentic_partial_grader_score(self):
        # Grader only reached 0.67 coverage → accuracy reflects that even if faithfulness is higher
        result = _FakeAgenticResult(
            retrieval_confidence=0.5,
            grader_scores=[0.67],
            best_grader_score=0.67,
        )
        hal = self._hal(sourced=3, unsourced=0)  # faithfulness = 1.0
        qs = compute_quality_score(result, hal)
        assert qs.dimensions.accuracy == pytest.approx(0.67)

    def test_agentic_empty_grader_scores_falls_back_to_faithfulness(self):
        # Grader never ran (empty list) → fall back to faithfulness like basic pipeline
        result = _FakeAgenticResult(
            retrieval_confidence=0.7,
            grader_scores=[],
            best_grader_score=0.0,
        )
        hal = self._hal(sourced=3, unsourced=0)  # faithfulness = 1.0
        qs = compute_quality_score(result, hal)
        assert qs.dimensions.accuracy == pytest.approx(1.0)

    def test_basic_pipeline_still_uses_faithfulness(self):
        # Basic result (no grader_scores attribute) → accuracy = faithfulness_score
        result = _FakeResult(retrieval_confidence=0.7)
        hal = self._hal(sourced=2, unsourced=2)  # faithfulness = 0.5
        qs = compute_quality_score(result, hal)
        assert qs.dimensions.accuracy == pytest.approx(0.5)
