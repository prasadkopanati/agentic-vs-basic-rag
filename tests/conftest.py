"""Shared fixtures for the test suite."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_llm_response():
    """A canned AIMessage-like response with usage metadata."""
    resp = MagicMock()
    resp.content = (
        "Credit unions must maintain a net worth ratio of at least 7% to be "
        "classified as well-capitalized under NCUA's prompt corrective action framework."
    )
    resp.usage_metadata = {"input_tokens": 250, "output_tokens": 60, "total_tokens": 310}
    return resp


@pytest.fixture
def mock_llm(mock_llm_response):
    """Patches ChatAnthropic in basic_rag so no Anthropic API calls are made."""
    with patch("pipelines.basic_rag.ChatAnthropic") as MockCls:
        instance = MagicMock()
        MockCls.return_value = instance
        instance.invoke.return_value = mock_llm_response
        yield instance
