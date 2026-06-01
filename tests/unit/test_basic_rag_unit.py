"""Unit tests for pure-logic helpers in the basic_rag pipeline.

No I/O, no network, no external services. Fast and deterministic.
"""

import pytest
from langchain_core.documents import Document

from pipelines.basic_rag import (
    BasicRAGResult,
    _build_chunks,
    _build_context_str,
    _compute_retrieval_confidence,
)


# ---------------------------------------------------------------------------
# _compute_retrieval_confidence
# ---------------------------------------------------------------------------


class TestComputeRetrievalConfidence:
    def test_single_chunk_returns_its_score(self):
        assert _compute_retrieval_confidence([0.8]) == pytest.approx(0.8)

    def test_multiple_chunks_returns_mean(self):
        result = _compute_retrieval_confidence([0.8, 0.6, 0.4, 0.2])
        assert result == pytest.approx(0.5)

    def test_empty_list_returns_zero(self):
        assert _compute_retrieval_confidence([]) == 0.0

    def test_all_zeros(self):
        assert _compute_retrieval_confidence([0.0, 0.0, 0.0]) == 0.0

    def test_all_ones(self):
        assert _compute_retrieval_confidence([1.0, 1.0, 1.0]) == pytest.approx(1.0)

    def test_order_does_not_affect_mean(self):
        assert _compute_retrieval_confidence([0.9, 0.1]) == pytest.approx(
            _compute_retrieval_confidence([0.1, 0.9])
        )


# ---------------------------------------------------------------------------
# _build_chunks
# ---------------------------------------------------------------------------


def _doc(source_file="test.md", text="regulatory text", chunk_index=0, url="", topic="general"):
    return Document(
        page_content=text,
        metadata={
            "source_file": source_file,
            "chunk_index": chunk_index,
            "source_url": url,
            "topic": topic,
        },
    )


class TestBuildChunks:
    def test_required_keys_present_for_hallucination_checker(self):
        chunks = _build_chunks([(_doc(), 0.75)])
        c = chunks[0]
        for key in ("chunk_id", "text", "source_url", "source_file", "topic", "cosine_similarity"):
            assert key in c, f"missing key: {key}"

    def test_chunk_id_contains_source_file_and_index(self):
        chunks = _build_chunks([(_doc("letter.md", chunk_index=3), 0.7)])
        assert "letter.md" in chunks[0]["chunk_id"]
        assert "3" in chunks[0]["chunk_id"]

    def test_cosine_similarity_stored_verbatim(self):
        chunks = _build_chunks([(_doc(), 0.85)])
        assert chunks[0]["cosine_similarity"] == pytest.approx(0.85)

    def test_text_preserved(self):
        chunks = _build_chunks([(_doc(text="NCUA capital adequacy"), 0.7)])
        assert chunks[0]["text"] == "NCUA capital adequacy"

    def test_multiple_docs_preserves_count(self):
        docs = [(_doc(f"d{i}.md", chunk_index=i), 0.5) for i in range(4)]
        chunks = _build_chunks(docs)
        assert len(chunks) == 4

    def test_source_url_passed_through(self):
        chunks = _build_chunks([(_doc(url="https://ncua.gov/letter"), 0.6)])
        assert chunks[0]["source_url"] == "https://ncua.gov/letter"

    def test_doc_without_chunk_index_uses_rank(self):
        doc = Document(page_content="text", metadata={"source_file": "x.md"})
        chunks = _build_chunks([(doc, 0.7)])
        # chunk_id should still be set (uses rank=0 as fallback)
        assert chunks[0]["chunk_id"] != ""


# ---------------------------------------------------------------------------
# _build_context_str
# ---------------------------------------------------------------------------


class TestBuildContextStr:
    def _chunk(self, source_file="doc.md", text="content"):
        return {
            "chunk_id": f"{source_file}_0",
            "text": text,
            "source_url": "",
            "source_file": source_file,
            "topic": "general",
            "cosine_similarity": 0.7,
        }

    def test_includes_document_number(self):
        ctx = _build_context_str([self._chunk()])
        assert "Document 1" in ctx

    def test_includes_source_file(self):
        ctx = _build_context_str([self._chunk(source_file="sar-faq.md")])
        assert "sar-faq.md" in ctx

    def test_includes_text(self):
        ctx = _build_context_str([self._chunk(text="suspicious activity")])
        assert "suspicious activity" in ctx

    def test_multiple_chunks_numbered_sequentially(self):
        chunks = [self._chunk(f"doc{i}.md", f"text {i}") for i in range(3)]
        ctx = _build_context_str(chunks)
        assert "Document 1" in ctx
        assert "Document 2" in ctx
        assert "Document 3" in ctx

    def test_empty_chunks_returns_empty_string(self):
        assert _build_context_str([]) == ""


# ---------------------------------------------------------------------------
# BasicRAGResult dataclass
# ---------------------------------------------------------------------------


class TestBasicRAGResult:
    def test_all_fields_accessible(self):
        r = BasicRAGResult(
            query="test query",
            answer="test answer",
            chunks=[],
            latency_s=1.5,
            input_tokens=100,
            output_tokens=50,
            retrieval_confidence=0.7,
        )
        assert r.query == "test query"
        assert r.answer == "test answer"
        assert r.latency_s == pytest.approx(1.5)
        assert r.retrieval_confidence == pytest.approx(0.7)

    def test_retrieval_confidence_label(self):
        # Retrieval confidence is the "cosine proxy" signal for basic RAG
        r = BasicRAGResult("q", "a", [], 1.0, 100, 50, 0.65)
        assert 0.0 <= r.retrieval_confidence <= 1.0


# ---------------------------------------------------------------------------
# regulatory_facts enrichment passthrough
# ---------------------------------------------------------------------------


class TestRegulatoryFactsPassthrough:
    def _doc_with_facts(self, facts, source_file="sar.md"):
        import json
        from langchain_core.documents import Document
        return Document(
            page_content="regulatory text",
            metadata={
                "source_file": source_file,
                "chunk_index": 0,
                "source_url": "",
                "topic": "BSA",
                "regulatory_facts": json.dumps(facts),
            },
        )

    def test_facts_decoded_from_json_string(self):
        doc = self._doc_with_facts(["SAR: $5,000 suspect identified"])
        chunks = _build_chunks([(doc, 0.8)])
        assert chunks[0]["regulatory_facts"] == ["SAR: $5,000 suspect identified"]

    def test_empty_facts_returns_empty_list(self):
        from langchain_core.documents import Document
        doc = Document(
            page_content="text",
            metadata={"source_file": "x.md", "chunk_index": 0},
        )
        chunks = _build_chunks([(doc, 0.7)])
        assert chunks[0]["regulatory_facts"] == []

    def test_context_str_shows_key_facts_line(self):
        chunk = {
            "chunk_id": "sar.md_0",
            "text": "raw text",
            "source_url": "",
            "source_file": "sar.md",
            "topic": "",
            "cosine_similarity": 0.7,
            "regulatory_facts": ["SAR: $5,000 suspect identified", "Deadline: 30 days"],
        }
        ctx = _build_context_str([chunk])
        assert "KEY FACTS:" in ctx
        assert "SAR: $5,000 suspect identified" in ctx
        assert "Deadline: 30 days" in ctx
        # Raw text still present after facts line
        assert "raw text" in ctx

    def test_context_str_no_key_facts_when_empty(self):
        chunk = {
            "chunk_id": "doc.md_0",
            "text": "content",
            "source_url": "",
            "source_file": "doc.md",
            "topic": "",
            "cosine_similarity": 0.7,
            "regulatory_facts": [],
        }
        ctx = _build_context_str([chunk])
        assert "KEY FACTS:" not in ctx

    def test_facts_line_appears_before_raw_text(self):
        chunk = {
            "chunk_id": "doc.md_0",
            "text": "raw text content",
            "source_url": "",
            "source_file": "doc.md",
            "topic": "",
            "cosine_similarity": 0.7,
            "regulatory_facts": ["threshold: 4%"],
        }
        ctx = _build_context_str([chunk])
        facts_pos = ctx.index("KEY FACTS:")
        text_pos = ctx.index("raw text content")
        assert facts_pos < text_pos
