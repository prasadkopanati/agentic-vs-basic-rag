"""Basic RAG pipeline: query → ChromaDB top-k → Claude → BasicRAGResult.

Single-shot retrieval with no iterative refinement — the intentional baseline
that agentic RAG is compared against.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_voyageai import VoyageAIEmbeddings

import config

# ---------------------------------------------------------------------------
# Module-level vectorstore cache — avoid re-embedding on every call
# ---------------------------------------------------------------------------

_vs: Chroma | None = None


def _get_vectorstore() -> Chroma:
    global _vs
    if _vs is None:
        embeddings = VoyageAIEmbeddings(
            model=config.EMBEDDING_MODEL,
            voyage_api_key=os.environ["VOYAGE_API_KEY"],
            batch_size=32,
        )
        _vs = Chroma(
            collection_name=config.CHROMA_COLLECTION_NAME,
            persist_directory=config.CHROMA_PERSIST_DIR,
            embedding_function=embeddings,
        )
    return _vs


# ---------------------------------------------------------------------------
# Pure-logic helpers (exported for unit testing)
# ---------------------------------------------------------------------------


def _compute_retrieval_confidence(similarities: list[float]) -> float:
    """Return mean cosine similarity as the retrieval confidence proxy."""
    if not similarities:
        return 0.0
    return sum(similarities) / len(similarities)


def _build_chunks(
    docs_and_scores: list[tuple[Document, float]],
) -> list[dict]:
    """Convert ChromaDB (doc, score) pairs into structured chunk dicts."""
    chunks = []
    for rank, (doc, score) in enumerate(docs_and_scores):
        meta = doc.metadata
        source_file = meta.get("source_file", "")
        chunk_index = meta.get("chunk_index", rank)
        facts_raw = meta.get("regulatory_facts", "[]")
        facts: list[str] = (
            json.loads(facts_raw) if isinstance(facts_raw, str) else (facts_raw or [])
        )
        chunks.append(
            {
                "chunk_id": f"{source_file}_{chunk_index}",
                "text": doc.page_content,
                "source_url": meta.get("source_url", ""),
                "source_file": source_file,
                "topic": meta.get("topic", ""),
                "cosine_similarity": score,
                "regulatory_facts": facts,
            }
        )
    return chunks


def _build_context_str(chunks: list[dict]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt.

    When pre-extracted regulatory_facts are present, they are shown before the
    raw text so LLMs can quickly confirm coverage without parsing dense prose.
    """
    if not chunks:
        return ""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        header = f"Document {i} [{chunk['source_file']}]"
        if chunk.get("topic"):
            header += f" — {chunk['topic']}"
        facts = chunk.get("regulatory_facts", [])
        facts_line = f"KEY FACTS: {' | '.join(facts)}\n" if facts else ""
        parts.append(f"{header}\n{facts_line}{chunk['text']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class BasicRAGResult:
    query: str
    answer: str
    chunks: list[dict]
    latency_s: float
    input_tokens: int
    output_tokens: int
    retrieval_confidence: float


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a compliance expert specializing in NCUA regulations and community banking law.
Answer the question using ONLY the context documents provided. If the answer is not
in the documents, say "I don't have enough information to answer this question."\
"""


def run_basic_rag(query: str) -> BasicRAGResult:
    t0 = time.perf_counter()

    vs = _get_vectorstore()
    docs_and_scores: list[tuple[Document, float]] = (
        vs.similarity_search_with_relevance_scores(query, k=config.TOP_K)
    )

    chunks = _build_chunks(docs_and_scores)
    similarities = [c["cosine_similarity"] for c in chunks]
    retrieval_confidence = _compute_retrieval_confidence(similarities)

    context_str = _build_context_str(chunks)
    llm = ChatAnthropic(
        model=config.LLM_MODEL,
        api_key=os.environ["ANTHROPIC_API_KEY"],
        temperature=0,
        max_tokens=512,
    )
    messages = [
        SystemMessage(content=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]),
        HumanMessage(content=f"Context:\n{context_str}\n\nQuestion: {query}\n\nAnswer:"),
    ]
    response = llm.invoke(messages)

    usage = response.usage_metadata or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    return BasicRAGResult(
        query=query,
        answer=response.content,
        chunks=chunks,
        latency_s=time.perf_counter() - t0,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        retrieval_confidence=retrieval_confidence,
    )


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    console = Console()

    queries = [
        "What is the net worth ratio required to be classified as well-capitalized?",
    ]

    for q in queries:
        console.print(f"\n[bold cyan]Query:[/bold cyan] {q}")
        result = run_basic_rag(q)
        console.print(f"[bold green]Answer:[/bold green] {result.answer}")
        console.print(
            f"[dim]Retrieval confidence: {result.retrieval_confidence:.3f} | "
            f"Tokens: {result.input_tokens}in / {result.output_tokens}out | "
            f"Latency: {result.latency_s:.2f}s[/dim]"
        )

        table = Table(title="Retrieved Chunks", show_lines=True)
        table.add_column("#", width=3)
        table.add_column("Source", style="cyan")
        table.add_column("Similarity", width=10)
        table.add_column("Excerpt", max_width=60)
        for i, chunk in enumerate(result.chunks, 1):
            table.add_row(
                str(i),
                chunk["source_file"],
                f"{chunk['cosine_similarity']:.4f}",
                chunk["text"][:120].replace("\n", " "),
            )
        console.print(table)
