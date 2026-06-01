# TODO — Agentic vs Basic RAG Demo

_Last updated: 2026-05-27_

---

## Current Query Status (10 queries in app.py)

| Query | Label | Agentic Wins? | Status |
|---|---|---|---|
| Q1 | Net worth ratio (well-capitalized) | Unclear — simple factual | Works |
| Q2 | BSA/AML program elements | Likely parity | Works |
| Q3 | SAR filing triggers and deadline | Likely parity | Works |
| Q4 | $500M asset threshold / audit requirements | Likely parity | Works |
| Q5 | Third-party vendor management | Likely parity | Works |
| **Q6** | **SAR structuring / PEP trap** | **Broken — see below** | **BROKEN (corpus gap)** |
| Q7 | IRR High rating: NEV threshold + DOR conditions | Broken — not adversarial | BROKEN (parity, needs redesign) |
| Q8 | Undercapitalized: mandatory commercial lending restrictions | Not viable | BROKEN (702.107 at rank #1) |
| **Q9** | **HMDA: residential lending reporting obligations** | **YES (designed)** | **Needs test with new prompts** |
| Q10 | Commercial RE appraisal: internal assessment vs. 12 CFR 722 | Not viable | BROKEN (appraisal docs in k=3) |

---

## Session Summary — 2026-05-27

### Code changes made (all in effect)

**`config.py`**:
- `TOP_K: int = 3` (was 4) — smaller k creates better vocabulary gaps
- `MAX_RETRIES: int = 6` (was 4) — demo story is about reliability, not cost/latency

**`pipelines/agentic_rag.py`** — multiple improvements:

1. **`_parse_grader_response` (parser bug fix)**: The parser now handles model responses that reason first and then state "Revised assessment: YES" or "YES" on its own line, instead of only catching responses that start with the word "YES". Previously the grader could correctly conclude YES in its reasoning but the parser would miss it (returning `False`) because the response didn't start with "YES".

2. **`_REWRITER_PROMPT_RETRY` (vocabulary translation)**: Added explicit instruction for the rewriter to translate "question vocabulary" (how the asker described the gap) into "document vocabulary" (the regulatory terms that appear in the answer document). Includes worked examples:
   - "formal written supervisory action" → Document of Resolution, DOR, written plan of action
   - "federal reporting obligation outside NCUA exam" → HMDA, Regulation C, Home Mortgage Disclosure Act
   - "collateral valuation for commercial loan" → Title XI, certified appraiser, 12 CFR Part 722
   - "mandatory lending restriction when undercapitalized" → 12 CFR 702.107, member business lending restriction
   - Also instructs rewriter to stay within NCUA/credit union vocabulary (do not import OCC, CCAR, Basel terms)

3. **`_GRADER_PROMPT` — new "Do NOT reject" rules added**:
   - **Table value is explicit**: A numeric value in a regulatory classification table (e.g., "High | Below 4%") is an unambiguous, explicit threshold — do not say it is "unclear" or "not confirmed" because narrative text doesn't separately restate it.
   - **Sub-procedure detail**: If documents identify that a compliance category applies (SAR filing, EDD, DOR consideration) and explain key conditions, do not require every sub-procedure or sub-regulation within that category unless the question explicitly names them. A document's disclaimer that a narrower sub-requirement (e.g., Section 312 PATRIOT Act) is outside its own scope does not make the answer incomplete.
   - **Automatic vs. conditional**: If a document states a requirement is case-by-case or depends on specific conditions, this directly answers "is it automatic?" — the answer is NO. Do not require a separate explicit statement "this is not automatic."
   - **Corpus document authority**: If a corpus document explicitly states that no unique additional requirement applies (e.g., "there is no supervisory expectation for unique PEP steps under the CDD rule"), that IS the answer. Do not override it with training-data knowledge of other frameworks.
   - **Reasoning-verdict consistency**: If your explanation finds all question dimensions adequately addressed, output YES. Do not output NO and then explain the question is answered.

4. **Output format constraint**: Grader prompt now requires the response to start with "YES" or "NO. Missing:" — no preamble before the verdict.

---

## Q6 Status — SAR structuring / PEP trap ❌ BROKEN

**Root cause — corpus gap, not grader/rewriter bug**:

The `joint-statement-23779b.md` document in the corpus explicitly states:
- "There is no regulatory requirement in the CDD rule, nor is there a supervisory expectation, for banks to have unique, additional due diligence steps for PEPs."
- "The CDD rule also does not require a bank to screen for or otherwise determine whether a customer or beneficial owner is a PEP."

The grader reads this and — knowing from training data that Section 312 of the USA PATRIOT Act imposes specific requirements for Senior Foreign Political Figures (SFPFs) — identifies a gap: the corpus covers general PEP/CDD obligations but explicitly says Section 312 is outside scope. It keeps requiring Section 312 SFPF documentation through all 6 retries.

The new "corpus document authority" rule partially helps but Haiku 4.5 still overrides the corpus statement with training-data knowledge of what should apply.

**Why Q6 previously "worked"**: Likely run with fewer corpus documents (before the joint-statement/CDD rule docs were added). Those documents now create an anti-signal that the grader reads as "Section 312 is missing."

**Fix options (choose one)**:
- **Option A (recommended)**: Add a FinCEN or NCUA guidance document on PEP/Section 312 account handling to the corpus. This would create the two-cluster trap: SAR FAQ (initial retrieval) → PEP/Section 312 doc (on retry), grader says YES.
- **Option B**: Redesign Q6 to remove the "senior government post abroad" (PEP) trigger and use a different two-cluster scenario. Loses the PEP narrative.
- **Option C**: Rephrase Q6 so it asks only about the SAR structuring obligation and uses EDD/CDD as the second dimension that the question explicitly limits to CDD rule scope (not Section 312). Higher risk of grader still requiring Section 312.

**TODO**:
- [ ] Option A: Fetch FinCEN guidance on PEP/senior foreign political figure accounts (31 CFR 1010.610 private banking rules). Add to corpus via `scripts/fetch_ncua_data.py` or direct download.
- [ ] After corpus addition, test Q6 for the original demo story: SAR FAQ initial → PEP/Section 312 doc on retry 1-2.

---

## Q7 Status — IRR High Rating: NEV Threshold + DOR Conditions ❌ BROKEN (needs redesign)

**Current query in app.py** (with "formal written supervisory finding or action commitment"):
- **Not adversarial**: With k=3, Basic RAG retrieves BOTH the NEV table chunk (rank #1, 0.6754) AND the DOR conditions chunk (rank #3, 0.6100) in a single shot. Basic RAG correctly answers both parts. No differentiation.
- **Root cause**: Both answers live in the same document (`irr-20procedures-20guidance-20internal-2a5960.md`). With k=3, chunks from the same doc cluster at similar similarity scores, and both clusters appear in the initial top-3.

**Examiner-next-step variant** (partial fix, not yet tested with new prompts):
- Query: "After our NCUA examination flagged our interest rate risk as High: (1) What is the specific post-shock NEV ratio that determines the High classification threshold? (2) Does the exam guidance specify that NCUA examiners have explicit discretion to close an exam without imposing corrective requirements on a High-rated credit union in certain defined situations?"
- **Initial retrieval**: Avoids DOR chunk — top-3 are NEV table, earnings/capital chunk, ENT assignment chunk. DOR chunk is at rank #4+.
- **Basic RAG**: Correctly answers Part 1 (NEV threshold) but says "I cannot find information" for Part 2.
- **Problem**: Previously the grader rejected even after finding the DOR chunk because "DOR not required" ≠ "exam closes without any requirements." The new grader rules (automatic requirement rule, corpus authority rule) may now fix this.
- **Status**: Not yet tested with the new prompt improvements. Test priority: HIGH.

**TODO**:
- [ ] Test examiner-next-step variant with improved grader — should now work in 1 retry given new "automatic requirement" rule and parser fix
- [ ] If examiner-next-step works: update Q7 query in `app.py` to that version
- [ ] If examiner-next-step still fails: redesign Q7 around a different two-cluster scenario with different documents (current IRR doc has both answers in same file — same-document limit)

**Architecture constraint**: Both NEV table and DOR conditions are in `irr-20procedures-20guidance-20internal-2a5960.md`. Any query that invokes both IRR classification AND DOR vocabulary will pull both from the same doc. True two-cluster traps require answers in DIFFERENT documents.

---

## Q8 Status — Undercapitalized: Mandatory Commercial Lending Restrictions ❌ NOT VIABLE

**Root cause**: `section-702-107-eb8a44.md` retrieves at rank #1 (sim ≥ 0.5) for every Q8 query formulation tested, regardless of how generic the vocabulary is. "4.5% net worth" + any lending/restriction vocabulary maps directly to 702.107. No vocabulary bridge creates a two-cluster gap where a PCA overview doc ranks above 702.107.

**TODO**:
- [ ] Either accept Q8 as parity (Basic RAG wins or ties) OR design a completely different scenario for slot Q8
- [ ] Candidate replacement: a scenario using the HELOC doc as first cluster + something else as second cluster (different from Q9 which uses HELOC → HMDA)

---

## Q9 Status — HMDA Reporting Obligation Hidden Behind HELOC Guidance ✅ (Design verified, new prompts not yet tested)

**Design confirmed working** (vocabulary separation verified in prior session):
- Initial retrieval: `lcu2005-07encl-08bbb8.md` (HELOC doc) exclusively at 0.59–0.54 for HELOC vocabulary
- HMDA vocabulary: `fair-lending-guide.pdf` exclusively at 0.70–0.65
- Clean vocabulary separation — zero overlap between clusters

**Concern with new prompts**: The new grader rules and rewriter vocabulary translation haven't been run against Q9. The prior issue (grader adding Call Report sub-question) was fixed in a prior session. New grader rules might help or introduce different rejection patterns.

**TODO**:
- [ ] Run Q9 with current prompts (including all 2026-05-27 changes): confirm initial retrieval → HELOC doc, grader identifies missing HMDA/Regulation C obligation, rewriter pivots to HMDA vocabulary, retry retrieves fair-lending-guide.pdf, grader says YES in 1-2 retries
- [ ] Compare Basic RAG Q9 score vs. Agentic RAG Q9 score on compliance-grade profile

---

## Q10 Status — Commercial RE Appraisal: Internal Assessment vs. 12 CFR 722 ❌ NOT VIABLE

**Root cause**: With k=3, all three slots retrieve appraisal-related documents regardless of vocabulary framing:
- `appraisals-home-equity-loans-87cd92.md`
- `collateral-htm-3ed59b.md` (commercial RE section mentions appraisals)
- `ag20190718item4b-733e16.md` (12 CFR 722 full rule)

Any query involving "commercial loan" + "collateral documentation" retrieves appraisal content directly. Basic RAG gets the 12 CFR 722 requirement ($1M threshold, certified appraiser) in its initial retrieval.

**TODO**:
- [ ] Either accept Q10 as parity OR redesign. One promising variant: "Q10-credit-file" framing (using "member business loan credit file" vocabulary without "appraisal") — `ag20190718item4b` drops out of top-3; only tested at retrieval level, not run through full pipeline yet.

---

## Grader Bugs — Updated Status

### Bug #1: Sensitivity sub-question ✅ FIXED
- Added rule: "do not require coverage of correlated metrics in the same table that the question never mentioned"
- Also added: "numeric value in regulatory classification table is an unambiguous, explicit threshold"
- Q7 grader now correctly accepts "Below 4%" from Figure 2 as the High classification threshold

### Bug #2: Phantom interaction mapping ⚠️ NOT ADDRESSED
- **Symptom**: Grader requires "mapping between frameworks" when question asks about two independent regulatory frameworks
- **Status**: No fix implemented. Affects Q8 dual-framework variant (not currently in use)

### Bug #3: Grader inconsistency / reasoning-verdict mismatch ✅ PARTIALLY FIXED
- **Parser fix**: `_parse_grader_response` now catches "Revised assessment: YES" and bare "YES" on its own line — previously returned `(False, "")` when grader reasoned correctly to YES but didn't start with the word YES
- **Prompt fix**: Added "reasoning-verdict consistency" rule to grader prompt — if your explanation shows all dimensions addressed, output YES
- **Remaining issue**: Haiku 4.5 still occasionally contradicts itself (says YES in reasoning, outputs NO in verdict). Parser fix is the more reliable safeguard.

### Bug #4 (New): Grader uses training-data knowledge to override corpus statements ⚠️ PARTIALLY FIXED
- **Symptom**: When corpus document explicitly says "requirement X does not apply," grader still requires X because training data says it should apply (e.g., Section 312 PATRIOT Act for PEP accounts)
- **Fix attempted**: Added "corpus document authority" rule to grader prompt
- **Status**: Rule is in prompt but Haiku 4.5 still overrides for Section 312 (Q6 failure). May need stronger language or model upgrade to Sonnet to fully resolve.

---

## Architecture Decisions (updated 2026-05-27)

- `TOP_K = 3` in `config.py` (changed from 4 — smaller k creates tighter vocabulary gaps for adversarial queries)
- `MAX_RETRIES = 6` in `config.py` (changed from 4 — demo story is about reliability, not cost/latency)
- Chunk accumulation across retries (unique by chunk_id) — critical, do not revert
- Three rewriter prompt variants: initial, retry (with vocabulary translation), dead-end (vocabulary reset)
- Separate LLM instances: rewriter/grader 512 tokens, generator 1024 tokens
- `grader_feedback: str` passed through AgentState to rewriter on retry
- `last_retrieval_novel_count: int` triggers dead-end rewriter when 0
- Grader output format: response MUST start with "YES" or "NO. Missing:"
- `_parse_grader_response`: handles "Revised assessment: YES", bare "YES" on its own line, first-sentence trimming of Missing feedback

---

## Demo Readiness Checklist

- [ ] **Q6**: Add Section 312 / PEP-specific corpus document; re-test for 2-retry demo story
- [ ] **Q7**: Test examiner-next-step variant with improved grader; update app.py if it works
- [ ] **Q9**: Run full agentic + basic pipeline test with current prompts; verify 1-2 retry story
- [ ] **Q8/Q10**: Either find working adversarial redesign or replace with different scenarios
- [ ] Run full 10-query evaluation (both pipelines) once ≥3 adversarial queries are confirmed
- [ ] Confirm Basic RAG scores ≤0.50 on Compliance-Grade for ≥3 adversarial queries
- [ ] Confirm Agentic RAG scores ≥0.75 on those same queries
- [ ] Streamlit app loads and renders correctly for all queries
- [ ] Update adversarial_scenarios.md if Q7/Q8/Q10 scenarios change

---

## KB-Grounded Grader Enhancement (2026-05-27) — see docs/plan_kb_grounded_grader.md

**Goal:** Ground the grader and rewriter in corpus knowledge to fix the Q11/Q12 score ceiling without relying solely on LLM parametric knowledge.

**Two artifacts to pre-compute at enrichment time:**
- `regulatory_facts` metadata per chunk (ChromaDB) — facts surfaced before raw text in grader context
- `artifacts/kb_manifest.json` — per-document vocabulary index for dynamic rewriter vocab injection

- [ ] **Create `scripts/enrich_chunks.py`**: fetch all chunks → Haiku fact extraction → `collection.update()` → write `artifacts/kb_manifest.json`
- [ ] **`pipelines/basic_rag.py`**: add `regulatory_facts` passthrough in `_build_chunks`
- [ ] **`pipelines/agentic_rag.py`** — three changes:
  - [ ] `_build_context_str`: show KEY FACTS before raw chunk text
  - [ ] add `_get_manifest_vocabulary(feedback, manifest)` function
  - [ ] update `_REWRITER_PROMPT_RETRY`: inject `{corpus_vocabulary}` from manifest at retry time
- [ ] Run `uv run python scripts/enrich_chunks.py` — verify ~78 doc entries in manifest, spot-check SAR $5,000 facts
- [ ] Run unit tests — 41/41 passing
- [ ] Dev mode Q11 test — grader context shows KEY FACTS; score moves above 0.67
- [ ] Prod mode Q11/Q12 test — Agentic wins (score ≥ 0.75, beats Basic)

---

## Corpus Status (as of 2026-05-27)

**Total**: ~1046 chunks from ~137 documents (unchanged since 2026-05-26 ingestion).

**Missing for Q6 fix**:
- FinCEN / NCUA guidance on PEP/SFPF accounts and Section 312 private banking rules (31 CFR 1010.610) — needed to create the clean two-cluster trap for Q6

**Still potentially missing**:
- §702.109 content (redirected to federalregister.gov)
- Detailed IRR corrective action supervisory expectations beyond the current irr-procedures doc
