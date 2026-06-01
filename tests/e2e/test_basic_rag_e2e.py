"""E2E tests for the basic_rag pipeline.

Calls real ChromaDB AND real Anthropic API. Requires:
  - ANTHROPIC_API_KEY in environment
  - VOYAGE_API_KEY in environment
  - ChromaDB populated via: uv run python ingest.py

Run with: pytest -m e2e
Deselect with: pytest -m 'not e2e'
"""

import pytest

import config
from pipelines.basic_rag import BasicRAGResult, run_basic_rag

# The five adversarial queries from docs/ground_truth.md
ADVERSARIAL_QUERIES = [
    "What is the net worth ratio required to be classified as well-capitalized?",
    "What BSA/AML program elements are credit unions required to maintain?",
    "What triggers a SAR filing requirement and what is the filing deadline?",
    "What audit requirements change for a credit union that crosses the $500M asset threshold?",
    "What are the NCUA's expectations for third-party vendor management in credit unions?",
]


@pytest.fixture(autouse=True)
def reset_vectorstore_cache():
    import pipelines.basic_rag as br
    original = br._vs
    br._vs = None
    yield
    br._vs = original


@pytest.mark.e2e
class TestBasicRagE2E:
    def test_q1_well_capitalized_ratio_returns_answer(self):
        result = run_basic_rag(ADVERSARIAL_QUERIES[0])
        assert isinstance(result, BasicRAGResult)
        assert len(result.answer) > 20
        # Ground truth: 7% net worth ratio for well-capitalized
        assert "7" in result.answer or "seven" in result.answer.lower()

    def test_q2_bsa_aml_returns_answer(self):
        result = run_basic_rag(ADVERSARIAL_QUERIES[1])
        assert isinstance(result, BasicRAGResult)
        assert len(result.answer) > 20

    def test_q3_sar_filing_returns_answer(self):
        result = run_basic_rag(ADVERSARIAL_QUERIES[2])
        assert isinstance(result, BasicRAGResult)
        assert len(result.answer) > 20

    def test_q4_audit_threshold_returns_answer(self):
        result = run_basic_rag(ADVERSARIAL_QUERIES[3])
        assert isinstance(result, BasicRAGResult)
        assert len(result.answer) > 20

    def test_q5_vendor_management_returns_answer(self):
        result = run_basic_rag(ADVERSARIAL_QUERIES[4])
        assert isinstance(result, BasicRAGResult)
        assert len(result.answer) > 20

    def test_all_queries_produce_top_k_chunks(self):
        for query in ADVERSARIAL_QUERIES:
            result = run_basic_rag(query)
            assert len(result.chunks) == config.TOP_K, (
                f"Expected {config.TOP_K} chunks for query: {query!r}"
            )

    def test_all_queries_have_positive_latency(self):
        for query in ADVERSARIAL_QUERIES:
            result = run_basic_rag(query)
            assert result.latency_s > 0.0

    def test_all_queries_retrieval_confidence_in_range(self):
        for query in ADVERSARIAL_QUERIES:
            result = run_basic_rag(query)
            assert 0.0 <= result.retrieval_confidence <= 1.0, (
                f"retrieval_confidence out of range for: {query!r}"
            )

    def test_token_counts_nonzero_for_all_queries(self):
        for query in ADVERSARIAL_QUERIES:
            result = run_basic_rag(query)
            assert result.input_tokens > 0, f"No input tokens for: {query!r}"
            assert result.output_tokens > 0, f"No output tokens for: {query!r}"
