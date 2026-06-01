# Adversarial Query Candidates — Comprehensive Analysis

**Purpose:** Identify all NCUA compliance questions where Basic RAG (k=3) will fail because the complete answer requires content from ≥3 distinct document clusters with genuine vocabulary gaps between them.

**Failure criterion:** Basic RAG retrieves the 3 most semantically similar chunks to the initial query. If the question requires content from clusters whose vocabulary doesn't appear in the query, those clusters will never rank in the top 3 — making a complete answer impossible regardless of LLM quality.

**Corpus state at time of writing (2026-05-26):** 72 OK documents.

---

## Why Basic RAG Fails: Architecture Review

With `TOP_K=3` and a single-shot retrieval, Basic RAG can reach at most ~3 document clusters per query. A question is adversarial when:

1. It requires **≥4 distinct source files** across **≥2 regulatory frameworks**
2. The source files use **different vocabulary** (so initial query doesn't rank all of them in top-3)
3. The answer contains **specific verifiable facts** (numbers, deadlines, thresholds) that can only come from documents in the missed clusters

Agentic RAG overcomes this because the Rewriter + Grader loop:
- Sees what's missing via grader feedback
- Pivots vocabulary to target the missing cluster
- Iterates up to `MAX_RETRIES=6` times

---

## New Documents Added to Corpus (14 new OK docs)

| Topic | File | Key Content |
|-------|------|-------------|
| `irr_supervisory_framework` | `updates-interest-rate-risk-supervisory-f-1e2da7.md` | NEV Test classifications (2022 revision), DOR triggers, CAMELS "S" |
| `sar_aml_faq_2021` | `answers-faqs-regarding-suspicious-activi-982460.md` | Keep-open requests, grand jury subpoenas, continuing SAR obligations |
| `hmda_regulation_c` | `home-mortgage-disclosure-act-regulation--a8b3da.md` | HMDA data fields, coverage thresholds, LAR requirements |
| `fair_lending_faq` | `faq-40c619.md` | ECOA, HMDA LAR error thresholds (10%/5%), disparate impact |
| `cybersecurity_exam` | `ncuas-information-security-examination-a-20a51f.md` | NCUA ISE assessment, ACET, FFIEC CAT |
| `cybersecurity_board` | `board-director-engagement-cybersecurity--6e199f.md` | Board cybersecurity oversight responsibilities |
| `supervisory_priorities_2026` | `ncuas-2026-supervisory-priorities-061787.md` | IRR, BSA/AML, lending, cybersecurity priorities |
| `mbl_commercial_loan_policy` | `commloanpolicy-htm-bd5325.md` | Single-borrower limits (15%+10%), portfolio concentration, underwriting |
| `irr_nev_method` | `nev-htm-2d62fe.md` | NEV methodology, present value, static vs. dynamic simulations |
| `irr_measurement_methods` | `methods-htm-8f2867.md` | IRR measurement methods overview (gap, NII, NEV comparison) |
| `mbl_loan_admin` | `administration-htm-1f6935.md` | Loan admin, lien perfection, covenant tracking, MIS |
| `bsa_reporting_recordkeeping` | `reportingrecordkeeping-htm-a16e3b.md` | SAR thresholds ($5K), filing deadlines (30/60 days), CTR ($10K) |
| `bsa_policies_procedures` | `bsapoliciesprocedures-htm-e9861c.md` | 4 BSA program elements, CDD, CIP, beneficial ownership |
| `mbl_policy_faq` | `have-questions-about-implementing-new-mb-d7b611.md` | MBL rule 2017 FAQ (469 chars — navigation stub, low value) |

---

## Tier 1: 100% Failure Guaranteed

These questions require ≥4 distinct document clusters with strong vocabulary gaps. Basic RAG at k=3 will definitively miss at least one cluster.

---

### Q-ADV-1 ⭐⭐⭐⭐⭐ [BEST DEMO CANDIDATE]

**Question:**
> "Under NCUA regulations, what are three specific numerical thresholds that credit union compliance officers must know: (a) the post-shock NEV ratio percentage below which a credit union is classified as 'high risk' under NCUA's 2022 revised NEV Supervisory Test for interest rate risk, (b) the maximum percentage of net worth a credit union may lend to a single commercial borrower when the excess above the standard limit is fully secured by readily marketable collateral, and (c) the minimum dollar amount of suspected money laundering transactions that triggers mandatory SAR filing when a suspect can be identified — and how many calendar days after detection the credit union has to file?"

**Why this is the best demo candidate:**
- Three specific numbers hidden across three completely different regulatory clusters
- Each number comes from a different document with different vocabulary
- A confident but incomplete answer from Basic RAG is obviously demonstrable
- Non-technical audiences (LinkedIn, YouTube) immediately understand what's missing

**Required documents:**

| Part | Source File | Specific Answer |
|------|-------------|-----------------|
| (a) NEV high-risk threshold | `updates-interest-rate-risk-supervisory-f-1e2da7.md` | Below **4%** post-shock NEV ratio OR above **65%** NEV sensitivity (2022 revised) |
| (b) Single-borrower max | `commloanpolicy-htm-bd5325.md` | **15%** standard + **10%** with readily marketable collateral = **25%** max |
| (c) SAR threshold + deadline | `reportingrecordkeeping-htm-a16e3b.md` | **$5,000** threshold; **30 days** from detection (60 days if no suspect) |

**Vocabulary gap analysis:**

| Cluster | Distinctive vocabulary | Would initial query retrieve? |
|---------|----------------------|-------------------------------|
| IRR supervisory framework | "NEV Supervisory Test", "post-shock NEV ratio", "high risk classification", "CAMELS S" | Only if query mentions "NEV" |
| MBL commercial loan policy | "single borrower limit", "readily marketable collateral", "Part 723", "15 percent net worth" | Only if query mentions "commercial loan" |
| BSA reporting | "SAR filing", "date of detection", "$5,000", "748.1(d)(1)", "FinCEN BSA E-Filing" | Only if query mentions "SAR" or "suspicious activity" |

**Basic RAG failure mode:** Query "NCUA compliance thresholds NEV SAR commercial loan" might retrieve 1-2 of these clusters but cannot reach all three at k=3. The answer will be missing at least one specific number. The LLM will either hallucinate the missing number or give a vague non-answer for that part.

**Agentic RAG path:**
1. Initial retrieval → gets IRR + one of the others
2. Grader: "Missing SAR dollar threshold and filing deadline" (score ~0.40)
3. Rewriter pivots: "SAR filing dollar threshold detection deadline BSA"
4. Retriever gets BSA reporting doc
5. Grader: "Missing MBL single-borrower maximum with collateral exception" (score ~0.70)
6. Rewriter pivots: "commercial loan single borrower limit 15 percent collateral Part 723"
7. Retriever gets MBL policy doc
8. Complete answer with all three numbers

---

### Q-ADV-2 ⭐⭐⭐⭐⭐

**Question:**
> "A federally insured credit union wants to approve a $3M commercial real estate loan to a single borrower where the amount would equal 20% of the credit union's net worth. Under NCUA regulations: (a) what specific conditions must be met to approve a commercial loan above the standard 15% single-borrower limit, and does commercial real estate qualify as 'readily marketable collateral' for this exception, (b) what appraisal standards must be satisfied for commercial real estate collateral under Part 722, and (c) what board-approved documentation is required when a credit union's commercial loan concentration to any single industry or type exceeds 100% of net worth?"

**Why this works:**
- Part (a) has a subtle trap: commercial real estate does NOT qualify as "readily marketable collateral" (CRE is illiquid, not daily-priced). Only highly liquid securities qualify. Basic RAG will likely miss this nuance.
- Parts (a), (b), and (c) require three different document clusters with distinct vocabulary.

**Required documents:**

| Part | Source File | Specific Answer |
|------|-------------|-----------------|
| (a) Exception conditions | `commloanpolicy-htm-bd5325.md` | Readily marketable collateral = liquid securities (US T-Bills, commercial paper <1 year). CRE does NOT qualify. Maximum is 25% only with truly liquid collateral. |
| (b) Part 722 appraisals | `ag20190718item4b-733e16.md` + `appraisals-home-equity-loans-87cd92.md` | FIRREA-compliant independent appraisal; state-certified appraiser; NCUA Part 722 requirements |
| (c) Concentration board rationale | `concentration-risk-2f8419.md` | Board must document rationale; "global perspective"; limits commensurate with net worth; 100%+ NW concentrations require careful monitoring and documented justification |

**Vocabulary gap analysis:**
- "single borrower limit 20 percent" → MBL policy (Part 723 vocabulary)
- "commercial real estate appraisal FIRREA Part 722 state certified" → Appraisal cluster (completely different vocabulary)
- "concentration risk board philosophy rationale 100 percent net worth" → Concentration risk doc (separate cluster)

**Basic RAG failure mode:** Initial retrieval on "commercial real estate single borrower limit" gets MBL policy docs but misses the appraisal cluster (which uses "appraisal", "FIRREA", "Part 722", "state-certified appraiser") and the concentration risk doc (which uses "concentration limits", "board philosophy", "global perspective").

---

### Q-ADV-3 ⭐⭐⭐⭐⭐

**Question:**
> "A credit union's commercial loan administration has three documented weaknesses discovered during examination: (1) collateral liens were not re-filed after UCC expiration at the 5-year mark, (2) financial covenant tracking was not enforced, and (3) annual borrower financial reviews were overdue by 14 months. Under NCUA guidance: (a) which of these does the NCUA Examiner's Guide explicitly identify as a 'loan administration system failure' that poses significant safety and soundness risk, (b) if the resulting unexpected charge-offs drop the credit union's net worth ratio to 5.5%, what PCA classification applies and what supervisory actions are immediately required, and (c) if the credit union falls into PCA due to assessment charges, what is the timeline for filing a Net Worth Restoration Plan?"

**Required documents:**

| Part | Source File | Specific Answer |
|------|-------------|-----------------|
| (a) Admin system failures | `administration-htm-1f6935.md` | All three are explicitly listed as loan administration system failures in the Examiner's Guide |
| (b) PCA at 5.5% net worth | `prompt-corrective-action-faqs-482f74.md` | 5.5% = "undercapitalized" (4%–6% range); specific mandatory and discretionary actions apply |
| (c) NWRP timeline | `nwrp-useful-tips-901756.md` | NWRP filing requirements, board approval, NCUA submission timeline |

**Vocabulary gap analysis:**
- "loan administration system failures UCC lien covenant annual review" → MBL admin cluster
- "net worth ratio 5.5 percent PCA undercapitalized prompt corrective action" → PCA cluster (completely different regulatory vocabulary)
- "net worth restoration plan NWRP filing timeline assessment" → NWRP cluster

**Basic RAG failure mode:** "commercial loan administration system failures PCA" retrieves MBL admin docs + maybe 1 PCA doc. The NWRP guidance is in a separate file with vocabulary ("net worth restoration", "NWRP", "board-approved plan") not present in the initial query.

---

### Q-ADV-4 ⭐⭐⭐⭐

**Question:**
> "Under current interagency guidance, a credit union has been filing SARs on a business member account for 18 months. The credit union then receives a written 'keep-open' request from a federal law enforcement agency for the same account, and separately receives a grand jury subpoena related to the same member. What is the credit union required to do: (a) must it continue filing continuing activity SARs during the period the keep-open request is active, (b) does receiving the grand jury subpoena alone — without observing additional suspicious activity — require a separate SAR filing, and (c) what are the four specific elements of a compliant BSA/AML program that NCUA examiners will verify under regulation §748.2?"

**Required documents:**

| Part | Source File | Specific Answer |
|------|-------------|-----------------|
| (a) + (b) Keep-open + grand jury | `answers-faqs-regarding-suspicious-activi-982460.md` | (a) YES — continuing SAR obligations persist during keep-open; (b) NO — grand jury subpoena alone does not require SAR |
| (c) Four BSA program elements | `bsapoliciesprocedures-htm-e9861c.md` | Internal controls, independent testing, designated responsible individual (AML/CFT officer), training |
| Supporting BSA context | `riskmanagement-htm-949bc6.md` or `customerduediligence-htm-605602.md` | CDD / enhanced due diligence for high-risk accounts |

**Vocabulary gap analysis:**
- "'keep-open' request law enforcement written SAR continuing" → SAR FAQ 2021 (new, distinctive vocabulary: "keep open", "written request")
- "grand jury subpoena SAR filing requirement" → same SAR FAQ 2021
- "BSA AML program four elements §748.2 internal controls" → BSA policies/procedures Examiner's Guide (different regulatory citation vocabulary)

**Basic RAG failure mode:** "SAR keep-open request law enforcement" retrieves the 2021 SAR FAQ. But the four BSA program elements are in a separate Examiner's Guide section with vocabulary like "§748.2", "internal controls", "AML/CFT officer" that doesn't appear in the SAR FAQ 2021.

---

### Q-ADV-5 ⭐⭐⭐⭐

**Question:**
> "A credit union mortgage department must simultaneously comply with three federal frameworks when originating home purchase loans. What are: (a) the four specific criteria under Regulation C that determine whether a credit union must file annual HMDA reports, (b) the sample error rate threshold at which NCUA requires mandatory correction and resubmission of a credit union's HMDA Loan Application Register during a fair lending examination, and (c) the BSA Customer Identification Program requirements that must be satisfied for any new mortgage borrower?"

**Required documents:**

| Part | Source File | Specific Answer |
|------|-------------|-----------------|
| (a) HMDA coverage criteria | `home-mortgage-disclosure-act-regulation--a8b3da.md` | 4 criteria: asset threshold exceeded; branch in MSA; originated ≥1 qualifying loan; originated ≥25 qualifying loans in each of 2 prior years |
| (b) LAR error thresholds | `faq-40c619.md` (Fair Lending FAQ) | 10% sample error rate OR 5% single data field error rate → mandatory resubmission |
| (c) BSA CIP for mortgages | `bsapoliciesprocedures-htm-e9861c.md` + `customerduediligence-htm-605602.md` | CIP: verify identity at account opening via §748.2(b)(2); ID collection, verification, recordkeeping |

**Vocabulary gap analysis:**
- "HMDA Regulation C coverage criteria annual report" → HMDA cluster
- "HMDA LAR error rate threshold resubmission fair lending examination" → Fair Lending FAQ (not the HMDA doc — a vocabulary gap WITHIN the fair lending space)
- "customer identification program BSA mortgage CIP §748.2" → BSA cluster

**Note:** Part (b) is particularly good because the error thresholds are in the Fair Lending FAQ — not the HMDA regulation C doc. Even if Basic RAG retrieves the HMDA doc perfectly, it won't have the specific 10%/5% thresholds.

---

## Tier 2: High Probability Failure

These questions will likely fail Basic RAG but with slightly smaller vocabulary gaps. Still strong for showing Agentic RAG's superiority.

---

### Q-ADV-6 ⭐⭐⭐⭐

**Question:**
> "NCUA's 2026 Supervisory Priorities identify IRR, lending quality, and BSA/AML as the top examination focus areas. For a credit union with $300M in assets preparing for examination: (a) what does 'risk-focused examination' mean vs 'defined scope examination' for credit unions at this asset size per the 2026 priorities letter, (b) what NEV post-shock ratio thresholds trigger enhanced IRR examination review steps specifically for $300M-$500M asset institutions under the 2022 supervisory framework, and (c) what BSA program governance elements will examiners specifically verify according to the NCUA Examiner's Guide section on BSA policies?"

**Required documents:** `supervisory_priorities_2026`, `updates-interest-rate-risk-supervisory-f-1e2da7.md`, `bsapoliciesprocedures-htm-e9861c.md`

**Why it works:** 2026 priorities gives the high-level framing; the specific NEV test thresholds for the $500M-$10B range are only in the 2022 IRR update; the specific BSA program elements are only in the Examiner's Guide.

---

### Q-ADV-7 ⭐⭐⭐⭐

**Question:**
> "What is Net Economic Value (NEV) analysis and how does it differ from income-based IRR measurement methods like gap analysis and NII simulation in terms of time horizon, what it captures, and its limitations? Additionally, what specific best practice risk limits should a credit union establish in its IRR policy for NEV-based measurements?"

**Required documents:** `nev-htm-2d62fe.md` (NEV methodology), `methods-htm-8f2867.md` (IRR measurement methods comparison), `irrprogram-htm-62374b.md` (IRR program requirements), `appendix-appendix-20a-1a9cb3.md` (741.3(b) Appendix A)

**Why it works:** NEV method doc covers what NEV is; measurement methods doc compares it to gap/NII; the policy risk limits (minimum post-shock NEV ratio, maximum % change) come from the NEV method doc as best practice guidance and the IRR program doc for regulatory requirements.

**Note:** This is more moderate because all four docs use consistent IRR/NEV vocabulary. Basic RAG might retrieve 3 of 4 naturally. Best for demonstrating partial-coverage failure rather than total failure.

---

### Q-ADV-8 ⭐⭐⭐

**Question:**
> "A credit union board of directors receives an examination finding that identifies inadequate oversight of cybersecurity risks. According to NCUA guidance: (a) what specific board-level cybersecurity governance responsibilities does NCUA's guidance enumerate, (b) what components of the NCUA Information Security Examination will assess whether board oversight is adequate, and (c) how do NCUA's 2026 supervisory priorities describe the examination focus for cybersecurity and information security?"

**Required documents:** `board-director-engagement-cybersecurity--6e199f.md`, `ncuas-information-security-examination-a-20a51f.md`, `supervisory_priorities_2026`

**Note:** This is a moderate adversarial question — the cybersecurity vocabulary is consistent across all three docs. Better as a supporting example than a primary demo question.

---

## Questions That Will NOT Work (Eliminated)

These fail the adversarial design test:

| Question | Why it fails |
|----------|--------------|
| "What is SAR filing?" | Answered by a single BSA doc; Basic RAG succeeds |
| "What is PCA?" | Single-doc lookup; no vocabulary gap needed |
| "What is NEV analysis?" | The NEV method doc covers this completely at k=3 |
| Q6 (PEP/Section 312) | Corpus doesn't have sufficient PEP/Section 312 content |
| "What are NCUA's 2026 priorities?" | Single-doc question; supervisory priorities doc covers it |
| Q7 original (BSA + OFAC) | Both use "compliance program" vocabulary; Basic RAG retrieves both |

---

## Implementation Recommendation

### Add in Priority Order

**Phase 1** (implement immediately, 100% structural guarantee):
- **Q-ADV-1** — Three specific numerical thresholds (NEV/MBL/SAR) ← primary demo
- **Q-ADV-2** — Single-borrower exception + appraisals + concentration board rationale
- **Q-ADV-3** — Loan admin failures → PCA consequences → NWRP timeline

**Phase 2** (add after Phase 1 validated):
- **Q-ADV-4** — SAR keep-open + grand jury + BSA program elements
- **Q-ADV-5** — HMDA coverage + LAR error thresholds + BSA/CIP

**Phase 3** (supporting examples):
- **Q-ADV-6** — 2026 Supervisory Priorities + IRR + BSA
- **Q-ADV-7** — NEV vs. gap analysis comparison

### Pre-Implementation Checklist for Each Question

Before adding a question to `app.py`:
1. Verify all required source files are in the corpus (`manifest.json` has no `error` field)
2. Run the question through Agentic RAG in isolation — confirm it reaches the correct answer
3. Run the same question through Basic RAG — confirm it is clearly incomplete or incorrect
4. Verify the specific numerical facts in the answer against the source documents
5. Confirm the grader's feedback message correctly identifies the missing dimension

### Corpus Gaps Still Outstanding

| Missing Content | Impact |
|-----------------|--------|
| MBL Examiner Guide Intro (`publishedguides.ncua.gov/examiner/content/examinersguide/Lending/MBL/Intro.htm`) | Low — content covered by Commercial Loan Policy + Admin docs |
| PEP/Section 312 private banking guidance | Blocks Q6; would need to add FinCEN private banking guidance |
| eCFR regulation text for §702.107/108 | PCA capital tiers have no actual regulatory text in corpus |
| NCUA Chartering and Field of Membership Manual | Needed for membership/FOM questions |

---

## Cross-Reference: Existing Questions in app.py

| Q# | Status | Action |
|----|--------|--------|
| Q1-Q5 | Working (in corpus, single-cluster) | Keep |
| Q6 | Blocked — PEP/Section 312 not in corpus | Do not add yet |
| Q7 | Vocabulary overlap — BSA answer in same cluster | Remove or replace with Q-ADV-4 |
| Q8 | Target doc always retrieves at k=3 (no gap) | Remove or replace with Q-ADV-1 |
| Q9 | HMDA/HELOC — test first with new grader format | Validate before keeping |
| Q10 | Single-doc lookup | Remove or replace with Q-ADV-2 |

---

*Generated: 2026-05-26 | Corpus: 72 documents | Targeted fetch: 14 new documents*
