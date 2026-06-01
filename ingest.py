"""Ingest sample_data/ into ChromaDB with voyage-law-2 embeddings.

Run: uv run python ingest.py
Idempotent: wipes and reloads the collection on each run.
"""

import os
import time
from pathlib import Path

import yaml
import chromadb
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_voyageai import VoyageAIEmbeddings
from langchain_chroma import Chroma
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

import config

console = Console()
SAMPLE_DATA = Path("sample_data")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[end + 3:].strip()


def _load_pdfs() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(SAMPLE_DATA.glob("*.pdf")):
        reader = PdfReader(str(path))
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                docs.append(Document(
                    page_content=text,
                    metadata={
                        "source_file": path.name,
                        "source_url": "",
                        "topic": "general",
                        "title": path.stem.replace("-", " ").title(),
                        "page": page_num + 1,
                    },
                ))
    return docs


def _load_markdown(path: Path, default_topic: str = "general") -> Document | None:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    if not body.strip():
        return None
    return Document(
        page_content=body,
        metadata={
            "source_file": path.name,
            "source_url": meta.get("url", ""),
            "topic": meta.get("topic", default_topic),
            "title": meta.get("title", path.stem),
        },
    )


def load_all_documents() -> list[Document]:
    docs: list[Document] = []

    docs.extend(_load_pdfs())

    for path in sorted(SAMPLE_DATA.glob("*.md")):
        doc = _load_markdown(path)
        if doc:
            docs.append(doc)

    letters_dir = SAMPLE_DATA / "ncua_letters"
    if letters_dir.exists():
        for path in sorted(letters_dir.glob("*.md")):
            doc = _load_markdown(path)
            if doc:
                docs.append(doc)

    return docs


def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
    return chunks


def build_vectorstore(chunks: list[Document]) -> Chroma:
    embeddings = VoyageAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        voyage_api_key=os.environ["VOYAGE_API_KEY"],
        batch_size=32,
    )

    # Wipe existing collection so re-runs are idempotent
    client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    try:
        client.delete_collection(config.CHROMA_COLLECTION_NAME)
        console.print("[dim]Deleted existing collection.[/dim]")
    except Exception:
        pass

    batch_size = 64
    total = len(chunks)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding + indexing chunks...", total=total)

        vectorstore: Chroma | None = None
        for start in range(0, total, batch_size):
            batch = chunks[start : start + batch_size]
            if vectorstore is None:
                vectorstore = Chroma.from_documents(
                    documents=batch,
                    embedding=embeddings,
                    collection_name=config.CHROMA_COLLECTION_NAME,
                    persist_directory=config.CHROMA_PERSIST_DIR,
                    collection_metadata={"hnsw:space": "cosine"},
                )
            else:
                vectorstore.add_documents(batch)
            progress.advance(task, len(batch))
            # Respect VoyageAI rate limit (120K tokens/min free tier)
            if start + batch_size < total:
                time.sleep(0.5)

    assert vectorstore is not None
    return vectorstore


def main() -> None:
    console.print("[bold]Loading documents...[/bold]")
    docs = load_all_documents()
    console.print(f"  Loaded [cyan]{len(docs)}[/cyan] source documents")

    console.print("[bold]Chunking...[/bold]")
    chunks = chunk_documents(docs)
    console.print(f"  Created [cyan]{len(chunks)}[/cyan] chunks "
                  f"(chunk_size={config.CHUNK_SIZE}, overlap={config.CHUNK_OVERLAP})")

    console.print("[bold]Embedding and indexing into ChromaDB...[/bold]")
    vectorstore = build_vectorstore(chunks)

    count = vectorstore._collection.count()
    console.print(f"\n[green bold]✓ Ingestion complete.[/green bold] "
                  f"[cyan]{count}[/cyan] chunks in collection "
                  f"[italic]{config.CHROMA_COLLECTION_NAME}[/italic] "
                  f"([dim]{config.CHROMA_PERSIST_DIR}[/dim])")


if __name__ == "__main__":
    main()
