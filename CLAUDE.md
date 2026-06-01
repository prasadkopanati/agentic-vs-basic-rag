# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

An open-source benchmark comparing **Basic RAG** vs **Agentic RAG** using banking/financial sector data (NCUA compliance documents). The output is a side-by-side quality comparison showing concretely where single-shot retrieval fails and where a multi-agent loop recovers.

Two delivery modes:
- **Streamlit** (`app.py`) — lightweight single-file demo, no server required
- **Full SPA** (`backend/` + `frontend/`) — FastAPI backend with Next.js frontend, runnable via Docker Compose

## Tech Stack

- **Orchestration:** LangGraph (multi-agent workflow)
- **LLM integration:** LangChain + Anthropic Claude (Haiku 4.5 in dev, Sonnet 4.6 in prod — `RAG_ENV=dev|prod`)
- **Embeddings:** `voyage-law-2` (both envs — legal/regulatory-optimized, negligible cost)
- **Language:** Python 3.12+
- **Vector store:** ChromaDB (local, zero-config)
- **Backend:** FastAPI with SSE streaming
- **Frontend:** Next.js 16 + React 19 + Tailwind CSS 4

## Architecture

Two parallel implementations run against the same banking knowledge base:

**Basic RAG** — single-shot pipeline:
```
User Query → Vector Retrieval (top-k) → LLM Generation → Answer
```

**Agentic RAG** — iterative multi-agent loop (defined in `docs/background.md`):
```
User Query → Rewriter → Retriever → Relevance Grader → Decision Router
                ↑                                              │
                └──── Retry Counter (budget enforcement) ─────┘ (if not relevant)
                                                               │ (if relevant)
                                                            Generator → Answer
```

### Agentic RAG Agents

| Agent | Responsibility |
|---|---|
| Query Rewriter | Rewrites raw user query into semantically richer form before retrieval |
| Retriever | Fetches semantically relevant documents from the knowledge base |
| Relevance Grader | Quality gate — explicitly judges whether retrieved docs actually answer the question |
| Decision Router | Routes to Generator (relevant) or back to Rewriter (not relevant, budget remaining) |
| Retry Counter | Enforces retry budget; triggers graceful fallback to Generator when exhausted |
| Generator | Synthesizes final answer from original question + best retrieved context |

## Retrieval Quality Score

Five-dimension weighted composite with three preset profiles (in `config.py`):

- **Compliance-Grade** — accuracy-first (50% accuracy, 30% source coverage) — default for this demo
- **High-Throughput** — speed-first (40% latency, 30% accuracy)
- **Cost-Optimized** — cost-first (40% cost, 25% latency)

See `docs/HLD.md` for full weight table.

## Knowledge Base

Domain: NCUA compliance and community banking (publicly available federal documents). Corpus: ~72 documents, ~739 chunks. Fetched and maintained by `scripts/fetch_ncua_data.py`.
