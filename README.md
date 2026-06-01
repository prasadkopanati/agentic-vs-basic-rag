# Agentic RAG vs Basic RAG — Banking Compliance Benchmark

A side-by-side benchmark that shows **where single-shot RAG fails** and **how an agentic multi-agent loop recovers** — using NCUA banking compliance documents as the knowledge base.

---

## Why This Exists

Classic RAG operates as a single-shot pipeline: query → retrieve → generate. It works for simple questions, but breaks down on complex, ambiguous, or cross-regulatory queries. This project makes that failure concrete and measurable.

Two pipelines run against the **same knowledge base** and the **same questions**:

| | Basic RAG | Agentic RAG |
|---|---|---|
| Approach | Single-shot: retrieve once, then generate | Iterative loop: rewrite → retrieve → grade → retry or generate |
| Query optimization | None — raw user query sent to vector store | Query Rewriter expands vocabulary and sharpens intent |
| Quality signal | None — retrieval is blindly trusted | Relevance Grader explicitly judges retrieved documents |
| Recovery | None — bad retrieval silently produces bad answer | Decision Router retries with revised query (budget-controlled) |
| Failure mode | Silent hallucination or miss | Graceful degradation after retry budget exhausted |

---

## Architecture

### Basic RAG
```
User Query → Vector Retrieval (top-k) → LLM Generation → Answer
```

### Agentic RAG
```
User Query → Rewriter → Retriever → Relevance Grader → Decision Router
                ↑                                              │
                └──── Retry Counter (budget enforcement) ─────┘ (if not relevant)
                                                               │ (if relevant)
                                                            Generator → Answer
```

Each agent has a narrow responsibility:

| Agent | Role |
|---|---|
| Query Rewriter | Rewrites raw query into semantically richer form before retrieval |
| Retriever | Fetches semantically relevant documents from ChromaDB |
| Relevance Grader | Quality gate — judges whether retrieved docs actually answer the question |
| Decision Router | Routes to Generator (relevant) or back to Rewriter (retries remaining) |
| Retry Counter | Enforces retry budget; triggers graceful fallback when exhausted |
| Generator | Synthesizes final answer from original question + best retrieved context |

Orchestration is implemented with **LangGraph**. See [`docs/background.md`](docs/background.md) for the full narrative and [`docs/HLD.md`](docs/HLD.md) for design decisions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Anthropic Claude (Haiku 4.5 in dev / Sonnet 4.6 in prod) |
| Orchestration | LangGraph |
| Embeddings | `voyage-law-2` (legal/regulatory-optimized) |
| Vector store | ChromaDB (local, zero-config) |
| Backend | FastAPI + SSE streaming |
| Frontend | Next.js 16 + React 19 + Tailwind CSS 4 |
| Simple demo | Streamlit (`app.py`) |

---

## Quick Start

### Option A — Streamlit (simplest)

```bash
# 1. Install dependencies (requires Python 3.12+)
uv sync          # or: pip install -e .

# 2. Set up environment
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY and VOYAGE_API_KEY

# 3. Build the knowledge base
python ingest.py

# 4. Run the demo
streamlit run app.py
```

### Option B — Full SPA (FastAPI + Next.js)

```bash
# 1. Set up environment
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY and VOYAGE_API_KEY

# 2. Build the knowledge base
uv run python ingest.py

# 3. Start both services
docker-compose up --build
```

Then open http://localhost:3000.

**Manual (no Docker):**
```bash
# Terminal 1 — backend
uv run uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

---

## Setup: API Keys

Copy `.env.example` to `.env` and fill in:

| Key | Required | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | [console.anthropic.com](https://console.anthropic.com) |
| `VOYAGE_API_KEY` | Yes | [dash.voyageai.com](https://dash.voyageai.com) |
| `RAG_ENV` | Yes | Set to `dev` (Haiku) or `prod` (Sonnet) |
| `TAVILY_API_KEY` | Scripts only | [app.tavily.com](https://app.tavily.com) — needed only to re-fetch NCUA docs |
| `FIRECRAWL_API_KEY` | Scripts only | [firecrawl.dev](https://firecrawl.dev) |
| `APIFY_TOKEN` | Scripts only | [apify.com](https://apify.com) |

The `TAVILY_API_KEY`, `FIRECRAWL_API_KEY`, and `APIFY_TOKEN` are **only needed if you want to re-fetch the NCUA knowledge base** via `scripts/fetch_ncua_data.py`. To run the demo with the pre-indexed corpus, only `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` are required.

---

## Knowledge Base

The knowledge base consists of publicly available NCUA (National Credit Union Administration) compliance documents — supervisory letters, examination procedures, and regulatory guidance.

To build the vector store from scratch:

```bash
# Fetch documents (requires Tavily/Firecrawl/Apify keys)
uv run python scripts/fetch_ncua_data.py

# Ingest into ChromaDB
uv run python ingest.py
```

Or run just the ingestion if documents are already in `sample_data/ncua_letters/`:

```bash
uv run python ingest.py
```

---

## Project Structure

```
├── app.py                  Streamlit demo (standalone)
├── config.py               LLM, embedding, and scoring config
├── ingest.py               ChromaDB ingestion
├── pipelines/
│   ├── basic_rag.py        Single-shot retrieval pipeline
│   └── agentic_rag.py      Multi-agent LangGraph pipeline
├── evaluation/
│   ├── hallucination.py    Hallucination detection
│   └── quality_score.py    5-dimension weighted quality scoring
├── backend/                FastAPI app (SSE streaming)
├── frontend/               Next.js 16 + React 19 SPA
├── scripts/
│   ├── fetch_ncua_data.py  Download and process NCUA documents
│   ├── capture_session.py  Batch benchmark runner
│   └── ...
├── tests/                  Unit, integration, and e2e tests
└── docs/                   Architecture, design decisions, benchmark results
```

---

## Evaluation

Each pipeline run is scored on five dimensions (configurable in `config.py`):

| Dimension | Default weight (Compliance-Grade profile) |
|---|---|
| Accuracy | 50% |
| Source coverage | 30% |
| Latency | 10% |
| Cost | 5% |
| Hallucination | 5% |

Three scoring profiles are available: **Compliance-Grade** (default), **High-Throughput**, and **Cost-Optimized**. See [`docs/HLD.md`](docs/HLD.md) for the full weight table.

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/background.md`](docs/background.md) | Problem statement and architecture narrative |
| [`docs/HLD.md`](docs/HLD.md) | High-level design, agent contracts, scoring model |
| [`docs/adversarial_scenarios.md`](docs/adversarial_scenarios.md) | Failure modes and adversarial query taxonomy |
| [`docs/agentic_rag_insights.md`](docs/agentic_rag_insights.md) | Live benchmark results and analysis |
| [`docs/ground_truth.md`](docs/ground_truth.md) | Ground truth answers for validation |

---

## License

MIT — see [LICENSE](LICENSE).
