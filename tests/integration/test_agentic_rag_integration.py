"""Integration tests for agentic_rag pipeline.

Uses real ChromaDB (must be populated) + mocked LLM.
Marked 'integration' — deselect with: pytest -m 'not integration'
"""

import pytest
from unittest.mock import MagicMock, patch

import config
from pipelines.agentic_rag import AgenticRAGResult, run_agentic_rag

_QUERY = "What is the net worth ratio required to be classified as well-capitalized?"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_caches():
    """Clear module-level LLM + graph caches between tests."""
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


def _make_llm_response(content: str, in_tok: int = 200, out_tok: int = 30) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok}
    return resp


# ---------------------------------------------------------------------------
# Tests — grader says YES on first pass (no retries)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAgenticRagNoRetry:
    """Grader says YES immediately — happy path."""

    def _mock_llm_sequence(self, MockCls, rewrite_resp, grade_resp, generate_resp):
        instance = MagicMock()
        MockCls.return_value = instance
        instance.invoke.side_effect = [rewrite_resp, grade_resp, generate_resp]
        return instance

    def test_returns_agentic_rag_result(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements for well-capitalized credit unions"),
                _make_llm_response("YES"),
                _make_llm_response("A credit union needs at least 7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        assert isinstance(result, AgenticRAGResult)

    def test_query_echoed(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        assert result.query == _QUERY

    def test_zero_retries_on_first_pass(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        assert result.retry_count == 0

    def test_retrieval_confidence_is_one_with_no_retries(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        assert result.retrieval_confidence == pytest.approx(1.0)

    def test_step_log_has_rewriter_retriever_grader_generator(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        nodes = [s["node"] for s in result.step_log]
        assert "rewriter" in nodes
        assert "retriever" in nodes
        assert "grader" in nodes
        assert "generator" in nodes
        assert "retry_counter" not in nodes

    def test_step_log_ordered_correctly(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        nodes = [s["node"] for s in result.step_log]
        assert nodes.index("rewriter") < nodes.index("retriever")
        assert nodes.index("retriever") < nodes.index("grader")
        assert nodes.index("grader") < nodes.index("generator")

    def test_chunks_populated_from_chromadb(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        assert len(result.chunks) == config.TOP_K
        for chunk in result.chunks:
            for key in ("chunk_id", "text", "source_file", "cosine_similarity"):
                assert key in chunk

    def test_token_counts_accumulate_across_nodes(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio", in_tok=100, out_tok=20),
                _make_llm_response("YES", in_tok=150, out_tok=5),
                _make_llm_response("7% net worth.", in_tok=300, out_tok=40),
            )
            result = run_agentic_rag(_QUERY)

        assert result.input_tokens == 550   # 100+150+300
        assert result.output_tokens == 65   # 20+5+40

    def test_latency_positive(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            result = run_agentic_rag(_QUERY)

        assert result.latency_s > 0.0

    def test_llm_called_three_times_no_retry(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            instance = self._mock_llm_sequence(
                MockCls,
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            )
            run_agentic_rag(_QUERY)

        assert instance.invoke.call_count == 3  # rewriter + grader + generator


# ---------------------------------------------------------------------------
# Tests — grader says NO on first pass (triggers retry)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAgenticRagWithRetry:
    """Grader says NO first, YES second — one retry cycle."""

    def test_one_retry_sets_retry_count_to_one(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.side_effect = [
                _make_llm_response("NCUA net worth ratio requirements"),  # rewriter 1
                _make_llm_response("NO"),                                  # grader 1
                _make_llm_response("NCUA 7% well-capitalized threshold"),  # rewriter 2 (retry)
                _make_llm_response("YES"),                                  # grader 2
                _make_llm_response("7% net worth ratio."),                  # generator
            ]
            result = run_agentic_rag(_QUERY)

        assert result.retry_count == 1

    def test_one_retry_reduces_retrieval_confidence(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.side_effect = [
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("NO"),
                _make_llm_response("NCUA 7% well-capitalized threshold"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            ]
            result = run_agentic_rag(_QUERY)

        # 1 retry with MAX_RETRIES=2 → 0.5
        assert result.retrieval_confidence == pytest.approx(0.5)

    def test_step_log_contains_retry_counter_on_retry(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.side_effect = [
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("NO"),
                _make_llm_response("NCUA 7% well-capitalized threshold"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            ]
            result = run_agentic_rag(_QUERY)

        nodes = [s["node"] for s in result.step_log]
        assert "retry_counter" in nodes

    def test_llm_called_five_times_on_one_retry(self):
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.side_effect = [
                _make_llm_response("NCUA net worth ratio requirements"),
                _make_llm_response("NO"),
                _make_llm_response("NCUA 7% well-capitalized threshold"),
                _make_llm_response("YES"),
                _make_llm_response("7% net worth ratio."),
            ]
            run_agentic_rag(_QUERY)

        assert instance.invoke.call_count == 5  # rewrite + grade + rewrite + grade + generate

    def test_budget_enforced_at_max_retries(self):
        """When grader always says NO, retry_count should not exceed MAX_RETRIES."""
        with patch("pipelines.agentic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            # Always NO — forces all retries to exhaust budget
            instance.invoke.side_effect = [
                _make_llm_response("rewrite 1"),   # rewriter 1
                _make_llm_response("NO"),           # grader 1
                _make_llm_response("rewrite 2"),   # rewriter 2 (retry 1)
                _make_llm_response("NO"),           # grader 2
                _make_llm_response("rewrite 3"),   # rewriter 3 (retry 2)
                _make_llm_response("NO"),           # grader 3 — budget exhausted here
                _make_llm_response("final answer"), # generator (forced)
            ]
            result = run_agentic_rag(_QUERY)

        assert result.retry_count == config.MAX_RETRIES
        assert len(result.answer) > 0  # always produces an answer
