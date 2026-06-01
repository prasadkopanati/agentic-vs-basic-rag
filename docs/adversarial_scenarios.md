# Adversarial Query Scenarios — Basic RAG Failure Analysis

Three structurally distinct failure modes where Basic RAG fails not by degree, but by architecture. Each is grounded in actual corpus documents.

---

## Scenario 1 — Three-Cluster Simultaneous Failure

**Failure type:** Architectural impossibility

**Query:**
> "This week three things landed on our desk: (1) our IRR model shows post-shock NEV dropped to 3.6%, (2) a member account received eight wire transfers of $4,700 each over the past month from an overseas sender, and (3) we just crossed $510M in total assets. What are our most time-sensitive regulatory obligations for each issue?"

**Why Basic RAG absolutely fails:**
The query embedding is a weighted average of three topic vocabularies — IRR measurement, structuring/BSA, and asset threshold supervision. With top-k=4, retrieved chunks fall near whichever cluster dominates the centroid (typically 1–2). The third cluster is unreachable in a single shot. The LLM hallucinates the missing obligation rather than flagging it as unanswered.

**Corpus documents required:**
| Cluster | Document | Key fact |
|---|---|---|
| IRR | `irr-20procedures-20guidance-20internal-2a5960.md` (lines 292–296) | NEV 3.6% → High rating; DOR evaluation required |
| BSA/SAR | `frequently-asked-questions-regarding-suspicious-activity-reporting-d226c4.md` | 8×$4,700 = structuring pattern → SAR within 30 days |
| Asset threshold | Fazio testimony docs | Crossing $500M → ONES supervision and exam schedule change |

**Stakes:** Missed BSA filing = federal violation. Missed exam obligation = supervisory finding. Unaddressed DOR = regulatory enforcement. All three carry independent consequences with different deadlines.

**Why agentic RAG wins:** Retriever initially returns one cluster. Grader identifies two missing regulatory dimensions. Rewriter pivots twice across retries, retrieving each missing cluster. Generator synthesizes all three with distinct deadlines per issue.

---

## Scenario 2 — HMDA Reporting Obligation Hidden Behind Residential Lending Guidance

**Failure type:** Operational guidance answer is correct but misses a mandatory federal reporting requirement from a separate regulatory framework

**Query (Q9 in demo):**
> "We've been expanding our home equity and first-lien residential mortgage programs. We have $340 million in total assets, branch offices in two metropolitan areas, and originated $45 million in first-lien home purchase loans and refinancings last year. We're confident our LTV limits and collateral standards are aligned with NCUA guidance. Our compliance team wants to know: are there any federal data collection or periodic reporting obligations that apply specifically to our residential real estate lending activities, beyond the standard NCUA examination process?"

**Why Basic RAG fails:**
"Home equity," "first-lien residential mortgage," "LTV limits," "collateral standards," "NCUA guidance" all map to the HELOC/residential lending cluster: `lcu2005-07encl-08bbb8.md` (33K chars, comprehensive HELOC guidance). That document covers LTV ratios, collateral policy, board oversight, concentration limits — and even mentions HMDA in a footnote as one of many applicable laws, without providing any HMDA requirements. Basic RAG returns a thorough answer about LTV and collateral standards, and the HMDA reporting obligation — which applies to this credit union with certainty — is never surfaced. The question "are there federal data collection or reporting obligations?" gets answered: "No additional obligations beyond NCUA examination."

**Corpus documents:**
| Cluster | Document | What it says |
|---|---|---|
| Initial retrieval | `lcu2005-07encl-08bbb8.md` | HELOC LTV limits, collateral standards, board MIS, concentration risk — mentions HMDA exists in a footnote only |
| Required second cluster | `fair-lending-guide.pdf` | HMDA/Regulation C section: three exemption conditions (no MSA office, assets below CFPB threshold, no first-lien loans prior year) — with $340M assets, MSA offices, and $45M in first-lien loans, ALL THREE exemptions fail → HMDA reporting required |

**Two-cluster mechanism:** "Home equity," "LTV," "collateral," "NCUA guidance" → HELOC doc cluster. "HMDA," "Regulation C," "home mortgage disclosure," "reporting obligations," "data collection" → fair-lending-guide.pdf cluster. These are completely separate embedding centroids with no vocabulary overlap. Basic RAG's single retrieval shot lands on the operational guidance cluster and never reaches the HMDA cluster. The grader catches that no federal data collection/reporting requirement is identified; the rewriter pivots to HMDA vocabulary on retry.

**Why agentic RAG wins:** After the HELOC-only answer grades LOW for missing federal reporting obligations, the rewriter targets HMDA/Regulation C vocabulary. The generator then applies the three-condition exemption test: $340M > CFPB threshold (not exempt), MSA offices present (not exempt), first-lien loans originated (not exempt) → HMDA reporting required for the prior calendar year.

**Stakes:** The credit union is required to file HMDA data with the CFPB. Missing HMDA filings result in examination findings, public CRA/HMDA penalties, and potential civil money penalties under Regulation C. The operational answer ("your LTV and collateral standards look fine") creates false assurance while an active federal reporting obligation goes undetected.

---

## Scenario 3 — Hidden Requirement in a Separate Regulatory Framework

**Failure type:** Query vocabulary locks retrieval to the wrong regulatory regime; a second mandatory framework is invisible to the retriever

**Query:**
> "We just originated a $2.8M commercial real estate loan secured by the borrower's warehouse. Our lending officer documented collateral value using an internal property assessment and a recent comparable sales summary. Does this documentation satisfy NCUA's collateral valuation requirements for a loan of this size?"

**Why Basic RAG absolutely fails:**
Every content word in the query maps to MBL/commercial lending documents: "commercial real estate loan," "collateral," "documentation" → `collateral-htm-3ed59b.md`, `aggregatelimit-htm-3a3f32.md`. Basic RAG retrieves those documents, which cover collateral standards for MBL loans. Those documents say nothing about the separate federal appraisal obligation. Basic RAG concludes the documentation is adequate — or gives a generic "appropriate collateral documentation required" answer — and the loan officer's approach is validated.

**Corpus document with correct answer:** `ag20190718item4b-733e16.md` — NCUA Final Rule, 12 CFR Part 722, Real Estate Appraisals (94K chars)

Under 12 CFR Part 722, commercial real estate transactions above $1,000,000 require a state-certified or state-licensed appraiser. An internal property assessment and a comparable sales summary do not satisfy this requirement. The loan as documented is non-compliant from origination.

**Two-framework gap:** The MBL aggregate limit rules (12 CFR Part 723) and the real estate appraisal rules (12 CFR Part 722) are independent regulatory frameworks that both apply to the same transaction. The MBL framework governs lending limits and collateral types; the appraisal framework governs how collateral *value* must be documented. Basic RAG retrieves one framework and never discovers the other exists.

**Why agentic RAG wins:** The grader rejects the MBL-only answer because the specific question — whether an internal assessment satisfies NCUA's *valuation documentation* requirement — is not answered from the MBL docs. The rewriter adds appraisal-specific vocabulary ("Title XI," "certified appraiser," "12 CFR 722"), retrieves the appraisal rule, and the generator correctly identifies that the internal assessment fails the $1M threshold requirement.

**Stakes:** Non-compliant loan on the books from day one. Examination finding, required remediation, possible write-down. The particularly damaging failure mode: the wrong answer is exactly what the lending team expected to hear.

---

## Failure Mode Summary

| # | Type | Basic RAG failure | Why architecture can't fix it |
|---|---|---|---|
| 1 | Architectural | Embedding centroid can't span 3 separate clusters in one shot | Top-k math — physically impossible with a single query vector |
| 2 | Hidden obligation | Operational guidance answer is correct but misses a mandatory federal reporting requirement | No mechanism to detect that a "complete" LTV/collateral answer left an HMDA reporting obligation unanswered |
| 3 | Framework | Vocabulary locks retrieval to one of two mandatory frameworks | Grader is the only thing that can notice the second framework exists |

Scenarios 2 and 3 are implemented as Q9 and Q10 in the demo query set. Scenario 1 is documented here for reference and can be added if a 3-retry demonstration is needed.
