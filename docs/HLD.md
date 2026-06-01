# High Level Design: Basic RAG vs Agentic RAG Demo

## Problem Statement

How might we help recruiters and potential freelance clients viscerally feel the reliability gap between basic and agentic RAG — using high-stakes banking data — in a way that builds enough trust to generate inbound leads?

---

## Goals

- Generate warm leads (recruiters, Upwork clients) by demonstrating authoritative RAG expertise
- Produce content artifacts (LinkedIn carousel, YouTube video, X post) from a single demo session
- Show value to a non-technical audience, not just technical correctness to engineers

## Non-Goals

- Cloud deployment of any kind
- A general-purpose RAG framework or library
- Optimizing for latency or cost at production scale
- Supporting arbitrary document types or domains

---

## The Core Insight

The demo's value is not in the architecture — it's in the **failure moment**. Audiences remember: *"The basic system confidently gave a bank the wrong regulation. The agentic system caught it and corrected itself."*

Everything in this design is built around making that moment as clear and credible as possible.

---

## Target Audience

| Audience | What They Need to See |
|---|---|
| Recruiter | Depth of expertise, domain credibility, polished output |
| Potential client (Upwork/LinkedIn) | Proof the problem is real, proof you solved it, ROI justification |

---

## Demo Narrative

**Scenario:** A compliance officer at a community bank asks five real questions. Some are ambiguous, some cross-document, some are traps designed to expose weak retrieval. Both systems answer each question. The audience watches what happens.

### The 5 Adversarial Queries (Pre-Designed)

These are chosen specifically because basic RAG fails on them in predictable, visible ways:

| # | Query | Why It's Hard |
|---|---|---|
| 1 | "What's the maximum loan-to-value ratio for a HELOC?" | Ambiguous — depends on loan type, state, and current NCUA guidance |
| 2 | "How do our BSA obligations change with the new FinCEN beneficial ownership rules?" | Cross-document — requires linking two separate regulatory sources |
| 3 | "What are current capital adequacy requirements for credit unions?" | Outdated-doc trap — knowledge bases often contain superseded versions |
| 4 | "What audit requirements change for a credit union that crosses the $500M asset threshold?" | Threshold-crossing implication — must infer that crossing $500M removes eligibility for the three lower-cost audit alternatives available to sub-$500M institutions |
| 5 | "Does a wire transfer to a politically exposed person require SAR filing?" | High-precision required — a wrong answer is a compliance violation |
| 6 | "One of our members holds a senior government post abroad and has been sending money to the same overseas business three times this month, each payment just below our standard wire review trigger. Our team approves each transfer individually. What distinct compliance categories does this pattern trigger — beyond standard wire transfer procedures — and what would a regulator expect us to have documented for this account?" | Two-cluster retrieval trap — PEP-first framing causes initial retrieval to land on enhanced due diligence docs (foreign official language matches PEP guidance); grader rejects because PEP docs don't cover the aggregation/structuring obligation implied by the repeated-payment pattern; rewriter pivots on retry toward suspicious activity reporting and transaction aggregation, finding the SAR FAQ; answer requires synthesizing both document clusters. Basic RAG retrieves PEP docs in a single shot and generates a confident but incomplete answer about enhanced monitoring, missing the SAR structuring obligation entirely. |
| 7 | "Our credit union's net economic value ratio dropped from 11% to 6% in a single quarter due to interest rate movements. At what specific NEV level does NCUA supervisory guidance require board notification, and what must a compliant interest rate risk action plan contain?" | Multi-document synthesis with vocabulary gap — NEV threshold is in the IRR policy letter, required action plan contents are in a separate supervisory examination guidance doc; Basic RAG retrieves one cluster and fabricates the other from model weights |

---

## Output Experience

**Delivery format: Streamlit app (runs locally, screen-recorded for content)**

No deployment. Run with `streamlit run app.py`. Screenshots and recordings become all content artifacts.

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  BANKING COMPLIANCE QUERY                                              │
│  [ Query selector dropdown ]  [ Profile: Compliance-Grade ▾ ]  [ Run Demo ]  │
├──────────────────────┬──────────────────────────────────────┤
│   BASIC RAG          │   AGENTIC RAG                        │
│                      │                                      │
│  ○ Retrieving...     │  ✓ [REWRITER] Query expanded         │
│                      │  ✓ [RETRIEVER] 4 docs fetched        │
│                      │  ✗ [GRADER] Relevance: LOW           │
│                      │  ↺ [RETRY 2] New query generated     │
│                      │  ✓ [GRADER] Relevance: HIGH          │
│                      │  ✓ [GENERATOR] Grounding answer...   │
│                      │                                      │
│  Answer:             │  Answer:                             │
│  [answer text]       │  [answer text]                       │
│                      │                                      │
│  ⚠ 2 unsourced       │  ✓ All claims sourced               │
│    claims detected   │    (3 documents cited)               │
├──────────────────────┴──────────────────────────────────────┤
│  RETRIEVAL QUALITY SCORE                                     │
│  Basic: ████░░░░░░  0.43     Agentic: ████████░░  0.81     │
├──────────────────────────────────────────────────────────────┤
│  Query 1: Basic 0.43 / Agentic 0.81                         │
│  Query 2: Basic 0.38 / Agentic 0.87   ← live-updating      │
│  Query 3: ...                           leaderboard         │
└──────────────────────────────────────────────────────────────┘
```

### Three Comparison Layers (in order of audience impact)

**1. Live Iteration Playback** — The highest-value differentiator
Show each agentic agent step as it executes. Basic RAG shows a spinner. Agentic RAG shows its reasoning: rewriting the query, grading relevance, retrying. The system visibly *thinks*. This is the moment non-technical audiences understand why agentic is different.

**2. Hallucination Checker** — The credibility signal
After each answer, a thin post-hoc layer checks every factual claim against the retrieved sources. Basic RAG frequently generates claims with no source document. Agentic RAG's answer is grounded. For banking clients, this maps directly to compliance liability — wrong answers aren't just embarrassing, they're expensive.

**3. Retrieval Quality Score** — The closing argument
A composite score shown after all 5 queries run. Gives non-technical viewers a single number to point to. Becomes the headline stat for LinkedIn ("Basic RAG: 0.41. Agentic RAG: 0.83. Same question. Same data.").

---

## Retrieval Quality Score

Five-dimension weighted composite. Rather than per-weight sliders, the score uses one of three **preset profiles** selected by a single dropdown. Each profile tells a different story for a different client type.

### Dimensions

| Dimension | How Measured |
|---|---|
| Answer Accuracy & Grounding | **Agentic pipeline:** `best_grader_score` — the running maximum grader score across all retrieval passes. The grader explicitly verifies whether every dimension of the question is covered, making it a direct completeness signal. **Basic pipeline:** `faithfulness_score` from the LLM-as-judge hallucination checker — fraction of answer claims that are verifiably grounded in retrieved source documents. |
| Source Coverage | Fraction of retrieved *source documents* cited in at least one supported claim. Uses document-level deduplication (multiple chunks from the same source file = one document) and a **pass-scoped denominator** for iterative pipelines. **Single-shot pipelines:** denominator = all unique source files retrieved. **Iterative pipelines** (agentic, chunks tagged with `retrieval_pass`): denominator = `cited_docs ∪ final_pass_docs` — exploratory-pass docs that were not cited are excluded, so navigating through intermediate document clusters is not penalised. Only unused docs from the final (most targeted) retrieval pass reduce the score. |
| Retrieval Confidence | **Basic RAG:** mean cosine similarity of top-k retrieved chunks — `mean(1 - cosine_distance_i for i in top_k)`. Requires ChromaDB collection created with `cosine` metric (set in `ingest.py`). Labeled "cosine proxy" in UI. **Agentic RAG:** retry-derived score — `1 - (retry_count / MAX_RETRIES)`, giving 1.0 (first-pass hit), 0.5 (1 retry), 0.0 (budget exhausted). Labeled "LLM grader" in UI. Both are [0,1] with the same direction (higher = better retrieval); labeled differently to be honest about the signal difference. |
| Latency | Time-to-answer in seconds, normalized against a 10s ceiling |
| Cost | Estimated token cost per query, normalized against a $0.10 ceiling: `score = max(0, 1 - actual_cost / 0.10)`. Ceiling accounts for 4–5 LLM calls in agentic pipeline at Sonnet pricing (~$0.05–$0.08/query). |

### Weight Profiles

| Dimension | Compliance-Grade | High-Throughput | Cost-Optimized |
|---|---|---|---|
| Answer Accuracy & Grounding | **50%** | 30% | 20% |
| Source Coverage | **30%** | 15% | 10% |
| Retrieval Confidence | 15% | 10% | 5% |
| Latency | 3% | **40%** | 25% |
| Cost | 2% | 5% | **40%** |
| | *"Get the answer right. Always."* | *"Speed drives UX."* | *"Run at scale on a budget."* |

**Compliance-Grade** is the default for this demo — it's the story that resonates with banking/regulatory clients. The other two profiles are shown in the YouTube video to illustrate that the score is a reusable framework, not a demo gimmick.

**Switching:** `WEIGHT_PROFILE = "compliance_grade" | "high_throughput" | "cost_optimized"` in `config.py`. Each profile is a plain `dict[str, float]`.

### Hallucination Checker Specification

| Property | Spec |
|---|---|
| **Model** | Same tier as generator: `claude-haiku-4-5-20251001` (dev) / `claude-sonnet-4-6` (prod), read from `config.py` |
| **Input contract** | `question: str`, `answer: str`, `chunks: list[dict]` where each chunk contains `chunk_id: str`, `text: str`, `source_url: str` |
| **Claim extraction** | Single structured prompt (one call): extract a numbered list of atomic factual claims, then for each claim output a JSON verdict. Conditional claims are treated as a single claim (e.g., "a SAR must be filed if the transaction exceeds $5,000" is one claim, not two). Retrieval-absence statements are excluded from claim extraction — phrases like "I cannot find guidance on X", "The documents do not address X", or "I don't have enough information about X" describe retrieval coverage, not verifiable regulatory facts, and are omitted from the claim list entirely. This prevents a pipeline that correctly admits ignorance from receiving unearned faithfulness credit. |
| **Output contract** | `HallucinationResult = {claims: list[ClaimResult], faithfulness_score: float, has_warning: bool \| None}` where `ClaimResult = {claim: str, sourced: bool, evidence_chunk_id: str \| None}`. `faithfulness_score = supported_claims / total_claims`; if `total_claims == 0`, `faithfulness_score = 1.0` (vacuously clean). |
| **Quality score integration** | `faithfulness_score` feeds the Answer Accuracy & Grounding dimension for the **basic pipeline** only. For the **agentic pipeline**, `best_grader_score` (the peak completeness score reached across all retrieval passes) is used instead — the grader directly evaluated whether every question dimension was covered, making it a more reliable accuracy proxy than post-hoc faithfulness checking on a multi-part answer. Both are continuous [0,1] signals; `faithfulness_score` is still computed and displayed for agentic answers (the ⚠/✓ badge) but does not feed the quality score. |
| **Badge rule** | `faithfulness_score < 1.0` → ⚠ badge with unsourced count; `faithfulness_score == 1.0` → ✓ badge with source count |
| **Graceful degradation** | On any LLM failure, log the error and return `HallucinationResult(claims=[], faithfulness_score=None, has_warning=None)` — UI shows **?** badge ("Grounding check unavailable"). Never return a false ✓. |
| **Temperature** | `0` — deterministic output required for consistent demo behavior |
| **Known limitation** | Same-model self-judging: the model that generated the answer judges it. Models exhibit agreement bias. Mitigated by structured JSON output that forces explicit per-claim verdicts with no room for rationalization. |

---

## System Architecture

### Basic RAG Pipeline

```
User Query
    │
    ▼
Vector Store (ChromaDB, local)
    │  top-k semantic search
    ▼
LLM (Claude Haiku 4.5 dev / Sonnet 4.6 prod) + retrieved context
    │
    ▼
Answer
```

### Agentic RAG Pipeline (LangGraph)

```
User Query
    │
    ▼
[Node: Query Rewriter]  — rewrites for semantic richness
    │
    ▼
[Node: Retriever]  — vector search on rewritten query
    │
    ▼
[Node: Relevance Grader]  — LLM judges: relevant or not?
    │
    ▼
[Node: Decision Router]
    ├── relevant → [Node: Generator] → Answer
    └── not relevant → [Node: Retry Counter]
                            ├── budget remaining → back to Rewriter
                            └── budget exhausted → Generator (graceful fallback)
```

Both pipelines share the same vector store, the same embedding model, and the same base LLM tier (Haiku in dev, Sonnet in prod). The only variable is the retrieval strategy.

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| UI | Streamlit | Runs locally, produces visual screenshots and recordings without deployment |
| Agent orchestration | LangGraph | Matches docs/background.md spec; production-grade multi-agent workflow |
| LLM | Claude Haiku 4.5 (dev) / Claude Sonnet 4.6 (prod) | Via `langchain-anthropic`; same API, different tier — dev is 37× cheaper, prod gives best answer quality for the final recording |
| Vector store | ChromaDB (local) | Zero-config, no cloud, persistent on disk |
| Embeddings | `voyage-law-2` (both dev and prod) | Voyage AI model trained on legal/regulatory text; embedding cost is negligible so no reason to downgrade in dev |
| Hallucination check | Custom LLM-as-judge prompt | Checks each answer claim against retrieved source chunks |
| Data ingestion | LangChain document loaders | PDF + markdown → chunks → ChromaDB |
| Language | Python 3.12+ | |

### Dev vs Prod Stack

The only difference between environments is the LLM tier. Everything else — embedding model, vector store, pipeline code, chunk strategy — is identical, so dev results are predictive of prod behavior.

| Layer | Dev | Prod |
|---|---|---|
| LLM | `claude-haiku-4-5-20251001` | `claude-sonnet-4-6` |
| Embeddings | `voyage-law-2` | `voyage-law-2` |
| Vector store | ChromaDB (local) | ChromaDB (local) |
| Reranker | None | None |

**Switching:** one env var — `RAG_ENV=dev` or `RAG_ENV=prod` — read in `config.py`. No other code changes.

**Cost rationale:** Haiku 4.5 is ~$0.08/M input vs Sonnet 4.6's $3.00/M — 37× cheaper. Over 20 dev experiments (~1.25M input tokens), that's ~$0.10 vs ~$3.75. The adversarial query failure behavior transfers reliably between tiers because both are Claude family models with the same instruction-following characteristics.

---

## Project Directory Structure

```
agentic_vs_basic_rag/
├── app.py                      # Streamlit entry point
├── config.py                   # RAG_ENV, model IDs, weight profiles, cost constants
├── ingest.py                   # Corpus ingestion → ChromaDB (idempotent)
├── pipelines/
│   ├── __init__.py
│   ├── basic_rag.py            # Single-shot retrieval + generation → BasicRAGResult
│   └── agentic_rag.py          # LangGraph multi-agent pipeline → AgenticRAGResult
├── evaluation/
│   ├── __init__.py
│   ├── hallucination.py        # LLM-as-judge per-claim checker → HallucinationResult
│   └── quality_score.py        # 5-dim weighted composite → QualityScore
├── scripts/
│   └── fetch_ncua_data.py      # Corpus fetch (Tavily + Apify + Firecrawl)
├── sample_data/
│   ├── *.pdf                   # 3 NCUA/federal PDFs
│   ├── *.md                    # 2 direct markdown docs
│   └── ncua_letters/           # 28 fetched NCUA letters (markdown + manifest.json)
├── docs/                       # HLD, background, gap analysis, ground truth, validation notes
├── tasks/                      # plan.md, todo.md
├── artifacts/                  # Screenshots and clips for content export (created at recording time)
├── pyproject.toml              # All dependencies, pinned versions (managed with uv)
├── uv.lock                     # Locked dependency tree
├── requirements.txt            # Data-fetch script deps only (legacy; consolidate into pyproject.toml)
├── .env                        # API keys (not committed)
├── .env.example                # Key names only (committed)
└── CLAUDE.md
```

---

## Knowledge Base

**Domain:** Community banking compliance (high-stakes, publicly available federal documents — no sensitivity concerns)

**Corpus (finalized):**

| Source | Type | Coverage |
|---|---|---|
| NCUA Fair Lending Guide (Dec 2025) | PDF, 55 pages | HELOC/LTV rules, fair lending requirements |
| NCUA CDRLF Congressional Report 2024 | PDF, 22 pages | Community development loan fund operations |
| Executive Order 14331 — Fair Banking (Aug 2025) | PDF, 3 pages | Most recent federal fair banking directive |
| NCUA Investment Pilot Program requirements | Markdown | Investment pilot regulations (ALM First / FCU loans) |
| Generic bank operations FAQ | Markdown | Fees, KYC, disputes, wire limits |
| 28 NCUA letters & guidance docs | Markdown (fetched) | BSA/AML (4), FinCEN/CDD (3), capital adequacy (4), HELOC/real estate (4), SAR filing (1), cybersecurity (1), exam schedule (2), interest rate risk (2), member business lending (3), PEP due diligence (1), concentration risk (1) |

**Corpus totals:** ~304K tokens across ~33 documents. All documents are publicly available at ncua.gov or federalregister.gov. No synthetic data needed.

**Ingestion strategy:**
- Chunk size: 512 tokens with 100-token overlap → ~739 chunks
- Metadata per chunk: source URL, topic, title, date fetched (enables citation tracing and temporal reasoning)
- NCUA letters fetched and maintained by `scripts/fetch_ncua_data.py`; re-runnable if corpus needs refresh

**All 7 adversarial query topics are covered:**
- Q1 LTV/HELOC → 4 documents (home equity lending risks, end-of-draw guidance, credit risk PDF, appraisal legal opinion)
- Q2 BSA/FinCEN → 7 documents (BSA program requirements, enforcement policy, FinCEN CDD rule, AML proposed rules, PEP due diligence)
- Q3 Capital adequacy → 4 documents (risk-based capital rule report, FAQs, webinar material, leverage ratio proposal)
- Q4 Asset threshold / audit requirements → 2 congressional Fazio testimonies; corpus confirms the $10M–$500M audit alternatives fact and the $500M threshold specifically
- Q5 SAR filing → SAR FAQ document (joint FinCEN/NCUA/FDIC/OCC guidance, Oct 2025)
- Q6 Structuring + PEP → SAR FAQ doc (aggregation/structuring rules), PEP due diligence doc, 4 BSA/AML docs, 3 FinCEN/CDD docs — answer requires cross-referencing structuring prohibition with PEP EDD from separate document clusters
- Q7 NEV / IRR action plan → 2 IRR docs (NEV threshold in policy letter) + exam schedule docs (required action plan contents) — answer spans two distinct document clusters with different embedding centroids

---

## Content Artifacts (from one demo session)

| Platform | Format | Key Hook |
|---|---|---|
| LinkedIn | 8-slide carousel | Slide 1: the failure. Slide 8: the score. Walk through the 5 queries in between. |
| YouTube | ~5 min screen recording | Live demo of all 5 queries, narrated. Show the agentic system retrying in real time. |
| X | 1 tweet + image | "Basic RAG answered 2/5 compliance questions correctly. Agentic RAG: 5/5. Here's why." + score screenshot |
| Upwork listing | Project description | Use the hallucination rate and quality score as the value proposition |

---

## MVP Scope

**In:**
- Streamlit UI with side-by-side comparison
- Basic RAG pipeline (single-shot)
- Agentic RAG pipeline (LangGraph: rewriter → retriever → grader → router → generator)
- Live agent step display for agentic pipeline
- Hallucination checker (LLM-as-judge, post-answer)
- Retrieval Quality Score (5-dimension weighted composite)
- 5 pre-designed adversarial banking queries
- ChromaDB local vector store with ~33 ingested documents (~304K tokens, ~739 chunks)

**Out:**
- Any cloud deployment
- User-supplied arbitrary queries (demo uses fixed query set)
- Reranking layer (keep it simple; the rewriter + grader do enough)
- User-supplied document uploads — corpus is fixed and pre-ingested
- Authentication or multi-user support

---

## Not Doing (and Why)

| Skipped | Reason |
|---|---|
| FastAPI / REST API | This is a demo, not a service. Streamlit is enough and produces better visuals. |
| Qdrant / Pinecone | ChromaDB runs locally with zero setup. Switching vector stores doesn't change the comparison story. |
| Streaming LLM output | Adds complexity; the live agent step display already provides the "thinking in real time" effect. |
| Open-source / third-party LLMs for prod | Worse answer quality muddies the comparison. Claude Sonnet is the prod constant; the pipeline is the variable. Haiku used in dev only. |
| Per-weight quality score sliders | Three preset profiles (Compliance-Grade, High-Throughput, Cost-Optimized) tell a cleaner story than 5 individual dials. |
| Separate embedding models for dev/prod | `voyage-law-2` used in both — embedding cost is negligible (<$0.20 total) and consistency across environments matters more than saving pennies. |
| Automated content publishing | Out of scope. Demo → record → post manually. |

---

## Key Assumptions to Validate

- [ ] The 5 adversarial queries actually cause basic RAG to fail visibly — test this early with real data before building the UI
- [ ] NCUA/FFIEC PDFs chunk and embed well enough for semantic retrieval to work at all — ingest and run a smoke test first
- [ ] The LLM-as-judge hallucination checker is reliable enough to trust its verdicts — calibrate against 10 manually verified answers
- [ ] Streamlit renders the side-by-side layout clearly enough for a LinkedIn screenshot — test on actual screen dimensions

---

## Success Criteria / Minimum Viable Score Gap

The demo is **ready to record** only when all three conditions are met on a `RAG_ENV=prod` run:

1. **Score gap:** Basic RAG scores ≤ 0.50 on the Compliance-Grade profile for at least 3 of 5 queries; Agentic RAG scores ≥ 0.75 on the same queries
2. **Hallucination gap:** At least 2 queries show a ⚠ hallucination warning on basic RAG and ✓ all claims sourced on agentic RAG for the same query
3. **No pipeline failures:** All 5 queries complete without API errors or timeouts

If the score gap is < 0.25 after the evaluation phase, investigate in this order before building the UI:
- Corpus coverage (re-run `fetch_ncua_data.py` for any under-covered topic)
- Generator prompt tuning (tighter grounding instruction reduces hallucination)
- Retry budget (increase `MAX_RETRIES` from 4 for harder queries — currently set to 4)
- Weight profile recalibration (check that dimension normalization ceilings are accurate)

---

## Resolved Decisions

| Question | Decision | Rationale |
|---|---|---|
| **Embedding model** | `voyage-law-2` (both dev and prod) | Voyage AI model purpose-built for legal/regulatory text; Anthropic-partnered; negligible cost (~$0.19 for all 20 experiments) makes a dev downgrade pointless |
| **Quality score weights** | Three preset profiles: Compliance-Grade, High-Throughput, Cost-Optimized | Cleaner than per-weight sliders; each profile maps to a real client conversation; switched with one config line |
| **Synthetic vs real data** | Real NCUA documents only | All 33 corpus documents are publicly available federal publications; no sensitivity or licensing concerns; fetched and maintained by `scripts/fetch_ncua_data.py` |
| **Dev LLM** | Claude Haiku 4.5 | Same provider and API as prod Sonnet; 37× cheaper; adversarial failure behavior transfers reliably between Claude tiers |
