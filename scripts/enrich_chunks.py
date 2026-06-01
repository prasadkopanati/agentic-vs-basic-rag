"""Post-ingestion corpus enrichment.

Extracts 3-6 structured regulatory facts from each chunk using Claude Haiku,
stores them as ChromaDB metadata (regulatory_facts), and writes a per-document
vocabulary manifest to artifacts/kb_manifest.json.

Run once after ingest.py, or after any corpus update:
    uv run python scripts/enrich_chunks.py

Cost: ~1,220 chunks × 300 tokens × Haiku rate ≈ $0.35–0.50 total.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict

import chromadb
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "ncua_compliance"
MANIFEST_PATH = "./artifacts/kb_manifest.json"
BATCH_SIZE = 20
RATE_LIMIT_SLEEP = 0.5  # seconds between batches

_EXTRACTION_PROMPT = """\
Extract the key regulatory facts from this banking compliance text.
Return ONLY a JSON object — no preamble, no explanation: {{"facts": ["fact1", "fact2"]}}

Rules:
- 3 to 6 facts maximum
- Each fact: 15 words or fewer
- Focus exclusively on: dollar thresholds, percentages, timeframes, \
regulatory citations (e.g. §748.1(d)(1)), and defined terms
- State the fact directly: "SAR threshold: $5,000 when suspect identified"
  NOT: "The document mentions a SAR threshold"
- Skip procedural steps, background context, or general guidance paragraphs
- If the chunk contains no measurable/citable facts, return {{"facts": []}}

TEXT:
{text}"""


def _extract_facts(client: Anthropic, text: str) -> list[str]:
    """Call Haiku to extract regulatory facts from a single chunk. Returns [] on failure."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            temperature=0,
            messages=[{"role": "user", "content": _EXTRACTION_PROMPT.format(text=text[:2000])}],
        )
        raw = response.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            facts = data.get("facts", [])
            return [str(f).strip() for f in facts if str(f).strip()][:6]
    except Exception:
        pass
    return []


def _build_manifest_entry(facts_by_chunk: list[list[str]]) -> dict:
    """Aggregate chunk-level facts into a document-level vocabulary entry."""
    topics: set[str] = set()
    thresholds: list[str] = []
    citations: list[str] = []
    timeframes: list[str] = []
    key_terms: list[str] = []

    for facts in facts_by_chunk:
        for fact in facts:
            fl = fact.lower()
            # Classify into manifest categories by content pattern
            if any(c in fact for c in ["$", "%", "ratio", "limit", "maximum", "minimum",
                                        "threshold", "aggregating", "or more", "or less"]):
                if fact not in thresholds:
                    thresholds.append(fact)
            elif any(c in fl for c in ["§", "cfr", "part ", "section ", "usc", ".1(", ".2("]):
                if fact not in citations:
                    citations.append(fact)
            elif any(c in fl for c in ["day", "month", "year", "hour", "deadline",
                                        "within ", "no later"]):
                if fact not in timeframes:
                    timeframes.append(fact)
            else:
                if fact not in key_terms:
                    key_terms.append(fact)

            # Infer topic tags from fact content
            topic_map = {
                "BSA": ["bsa", "bank secrecy", "suspicious activity", "sar", "currency transaction",
                        "fincen", "aml", "anti-money"],
                "SAR": ["sar", "suspicious activity report", "reportable activity"],
                "CTR": ["ctr", "currency transaction report", "10,000", "$10,000"],
                "IRR": ["irr", "interest rate risk", "nev", "net economic value",
                        "earnings at risk", "rate shock"],
                "PCA": ["pca", "prompt corrective action", "net worth ratio",
                        "well-capitalized", "undercapitalized"],
                "Commercial_Lending": ["member business", "commercial loan", "part 723",
                                        "net worth limit", "collateral"],
                "HMDA": ["hmda", "home mortgage disclosure", "regulation c", "reporting obligation"],
                "Appraisals": ["appraisal", "12 cfr 722", "certified appraiser", "title xi"],
                "Cybersecurity": ["cybersecurity", "incident response", "data breach", "ransomware"],
                "Capital": ["net worth", "risk-based capital", "leverage ratio", "complex credit union"],
            }
            for topic, keywords in topic_map.items():
                if any(kw in fl for kw in keywords):
                    topics.add(topic)

    return {
        "topics": sorted(topics),
        "thresholds": thresholds[:15],
        "citations": citations[:15],
        "timeframes": timeframes[:10],
        "key_terms": key_terms[:15],
    }


def enrich(dry_run: bool = False) -> None:
    """Main enrichment entry point."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    chroma = chromadb.PersistentClient(path=CHROMA_DIR)
    col = chroma.get_collection(COLLECTION_NAME)

    total = col.count()
    print(f"Enriching {total} chunks in '{COLLECTION_NAME}'...")

    # Fetch all chunks (ChromaDB returns up to limit per call; page through if needed)
    all_results = col.get(limit=total, include=["documents", "metadatas"])
    ids = all_results["ids"]
    texts = all_results["documents"]
    metas = all_results["metadatas"]

    # Group chunks by source_file for manifest building
    doc_chunks: dict[str, list[list[str]]] = defaultdict(list)

    # Process in batches; flush each batch immediately to ChromaDB
    total_facts = 0
    skipped = 0

    for batch_start in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[batch_start:batch_start + BATCH_SIZE]
        batch_texts = texts[batch_start:batch_start + BATCH_SIZE]
        batch_metas = metas[batch_start:batch_start + BATCH_SIZE]

        batch_updated_ids: list[str] = []
        batch_updated_metas: list[dict] = []

        for chunk_id, text, meta in zip(batch_ids, batch_texts, batch_metas):
            src = meta.get("source_file", "?")
            existing = meta.get("regulatory_facts")
            if existing:
                # Already enriched — accumulate for manifest but skip LLM call
                skipped += 1
                stored = json.loads(existing) if isinstance(existing, str) else existing
                doc_chunks[src].append(stored)
                continue

            facts = [] if dry_run else _extract_facts(client, text or "")
            total_facts += len(facts)
            doc_chunks[src].append(facts)

            if not facts:
                # Nothing to store — skip update for this chunk
                continue

            new_meta = dict(meta)
            # Store as JSON string — ChromaDB metadata values must be str/int/float/bool;
            # empty list is also rejected, so we only write non-empty facts.
            new_meta["regulatory_facts"] = json.dumps(facts)

            batch_updated_ids.append(chunk_id)
            batch_updated_metas.append(new_meta)

        completed = min(batch_start + BATCH_SIZE, len(ids))
        print(f"  Processed {completed}/{len(ids)} chunks "
              f"(+{total_facts} facts, {skipped} already-enriched skipped)")

        if not dry_run and batch_updated_ids:
            col.update(ids=batch_updated_ids, metadatas=batch_updated_metas)

        if batch_start + BATCH_SIZE < len(ids):
            time.sleep(RATE_LIMIT_SLEEP)

    print(f"\nExtracted {total_facts} facts across {len(ids) - skipped} new chunks "
          f"({skipped} already enriched).")

    # Build kb_manifest.json
    manifest: dict[str, dict] = {}
    for source_file, chunks_facts in sorted(doc_chunks.items()):
        manifest[source_file] = _build_manifest_entry(chunks_facts)

    if not dry_run:
        os.makedirs(os.path.dirname(MANIFEST_PATH) if os.path.dirname(MANIFEST_PATH) else ".", exist_ok=True)
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Manifest written: {MANIFEST_PATH} ({len(manifest)} documents)")
    else:
        print(f"[DRY RUN] Would write manifest with {len(manifest)} documents")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich corpus chunks with regulatory facts")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip LLM calls and ChromaDB writes; show counts only")
    args = parser.parse_args()
    enrich(dry_run=args.dry_run)
