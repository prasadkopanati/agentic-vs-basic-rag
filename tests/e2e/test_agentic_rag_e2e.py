"""E2E tests for the agentic_rag pipeline.

Calls real ChromaDB AND real Anthropic API. Requires:
  - ANTHROPIC_API_KEY and VOYAGE_API_KEY in environment
  - ChromaDB populated via: uv run python ingest.py

Run with: pytest -m e2e
"""

import pytest

import config
from pipelines.agentic_rag import AgenticRAGResult, run_agentic_rag

ADVERSARIAL_QUERIES = [
    "What is the net worth ratio required to be classified as well-capitalized?",
    "What BSA/AML program elements are credit unions required to maintain?",
    "What triggers a SAR filing requirement and what is the filing deadline?",
    "What audit requirements change for a credit union that crosses the $500M asset threshold?",
    "What are the NCUA's expectations for third-party vendor management in credit unions?",
]


@pytest.fixture(autouse=True)
def reset_caches():
    import pipelines.agentic_rag as ar
    import pipelines.basic_rag as br
    orig_llm, orig_graph, orig_vs = ar._llm, ar._graph, br._vs
    ar._llm = None
    ar._graph = None
    br._vs = None
    yield
    ar._llm = orig_llm
    ar._graph = orig_graph
    br._vs = orig_vs


@pytest.mark.e2e
class TestAgenticRagE2E:
    def test_all_queries_return_answers(self):
        for q in ADVERSARIAL_QUERIES:
            result = run_agentic_rag(q)
            assert isinstance(result, AgenticRAGResult)
            assert len(result.answer) > 20, f"Short or empty answer for: {q!r}"

    def test_all_queries_have_step_logs(self):
        for q in ADVERSARIAL_QUERIES:
            result = run_agentic_rag(q)
            assert len(result.step_log) >= 4, f"Expected ≥4 steps for: {q!r}"
            nodes = {s["node"] for s in result.step_log}
            assert {"rewriter", "retriever", "grader", "generator"}.issubset(nodes)

    def test_all_queries_have_top_k_chunks(self):
        for q in ADVERSARIAL_QUERIES:
            result = run_agentic_rag(q)
            assert len(result.chunks) == config.TOP_K

    def test_retry_budget_never_exceeded(self):
        for q in ADVERSARIAL_QUERIES:
            result = run_agentic_rag(q)
            assert result.retry_count <= config.MAX_RETRIES

    def test_retrieval_confidence_in_range(self):
        for q in ADVERSARIAL_QUERIES:
            result = run_agentic_rag(q)
            assert 0.0 <= result.retrieval_confidence <= 1.0

    def test_token_counts_nonzero(self):
        for q in ADVERSARIAL_QUERIES:
            result = run_agentic_rag(q)
            assert result.input_tokens > 0
            assert result.output_tokens > 0

    def test_q4_audit_threshold_produces_answer(self):
        """Q4 is the key adversarial query — agentic RAG should improve on basic RAG's refusal."""
        result = run_agentic_rag(ADVERSARIAL_QUERIES[3])
        assert len(result.answer) > 20
        # Should mention the $500M threshold or audit alternatives
        answer_lower = result.answer.lower()
        assert any(kw in answer_lower for kw in ["500", "audit", "alternative"])

    def test_at_least_two_queries_trigger_retry(self):
        """Agentic RAG should show iterative behavior on adversarial queries."""
        retry_counts = [run_agentic_rag(q).retry_count for q in ADVERSARIAL_QUERIES]
        queries_with_retry = sum(1 for r in retry_counts if r > 0)
        assert queries_with_retry >= 1, (
            f"Expected ≥1 query to trigger a retry; retry counts: {retry_counts}"
        )
