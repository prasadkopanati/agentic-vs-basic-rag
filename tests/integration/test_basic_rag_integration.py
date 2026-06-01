"""Integration tests for basic_rag pipeline.

Uses the real ChromaDB collection (must be populated by ingest.py first) but
mocks the LLM so no Anthropic API calls are made. Marked 'integration' so
they can be deselected with: pytest -m 'not integration'
"""

import pytest
from unittest.mock import MagicMock, patch

import config
from pipelines.basic_rag import BasicRAGResult, run_basic_rag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPLIANCE_QUERY = (
    "What is the net worth ratio required to be classified as well-capitalized?"
)


@pytest.fixture(autouse=True)
def reset_vectorstore_cache():
    """Clear the module-level _vs cache between tests to avoid cross-test leakage."""
    import pipelines.basic_rag as br
    original = br._vs
    br._vs = None
    yield
    br._vs = original


@pytest.fixture
def mock_llm_invoke():
    resp = MagicMock()
    resp.content = (
        "A credit union must maintain a net worth ratio of at least 7% "
        "to be classified as well-capitalized under NCUA's PCA framework."
    )
    resp.usage_metadata = {"input_tokens": 300, "output_tokens": 45, "total_tokens": 345}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRunBasicRagIntegration:
    def test_returns_basic_rag_result(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert isinstance(result, BasicRAGResult)

    def test_query_echoed_in_result(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert result.query == _COMPLIANCE_QUERY

    def test_answer_comes_from_llm(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert result.answer == mock_llm_invoke.content

    def test_chunks_count_matches_top_k(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert len(result.chunks) == config.TOP_K

    def test_chunks_have_required_keys(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        for chunk in result.chunks:
            for key in ("chunk_id", "text", "source_url", "source_file", "topic", "cosine_similarity"):
                assert key in chunk, f"chunk missing key: {key}"

    def test_retrieval_confidence_in_unit_interval(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert 0.0 <= result.retrieval_confidence <= 1.0

    def test_token_counts_populated(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert result.input_tokens == 300
        assert result.output_tokens == 45

    def test_latency_is_positive(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        assert result.latency_s > 0.0

    def test_retrieval_finds_relevant_sources(self, mock_llm_invoke):
        """Verify ChromaDB returns compliance-domain documents for a compliance query."""
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        source_files = [c["source_file"] for c in result.chunks]
        # At least one chunk should come from a .md or .pdf source
        assert any(f.endswith(".md") or f.endswith(".pdf") for f in source_files)

    def test_cosine_similarities_are_positive(self, mock_llm_invoke):
        """similarity_search_with_relevance_scores returns 1-distance in [0,1]."""
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            result = run_basic_rag(_COMPLIANCE_QUERY)

        for chunk in result.chunks:
            assert chunk["cosine_similarity"] >= 0.0

    def test_llm_called_once_per_query(self, mock_llm_invoke):
        with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
            instance = MagicMock()
            MockCls.return_value = instance
            instance.invoke.return_value = mock_llm_invoke

            run_basic_rag(_COMPLIANCE_QUERY)

        instance.invoke.assert_called_once()
