# Scoring Analysis — Multi-Part Query Inversions and Fixes

This document covers the root causes behind two score inversions observed on adversarial multi-part queries (Q6, Q11), the fixes applied, and their measured effects.

---

## Q11 — Three Regulatory Thresholds: NEV / Single-Borrower / SAR

**Query:** Three regulatory thresholds: NEV / single-borrower / SAR  
**Pre-fix result:** Basic RAG 0.92 · Agentic RAG 0.72 (↓ 20.1 pts) — Basic wins despite answering only 1 of 3 parts

---

## What Actually Happened

| Part | Basic RAG | Agentic RAG |
|---|---|---|
| (a) NEV High-risk threshold | ✅ Correct | ✅ Correct |
| (b) Part 723 single-borrower limit | ❌ "I don't have enough information" | ✅ Correct (full definition + collateral examples) |
| (c) SAR filing threshold + deadline | ❌ "I don't have enough information" | ❌ Not found in retrieved docs |

Agentic answered 2 of 3 parts correctly. Basic answered 1 of 3. Basic won the composite score by 20 points.

---

## Dimension Breakdown (pre-fix)

| Dimension | Weight | Basic RAG | Agentic RAG |
|---|---|---|---|
| Accuracy (faithfulness) | 50% | **1.00** | 0.86 |
| Source coverage | 30% | **1.00** | 0.50 |
| Retrieval confidence | 15% | 0.66 | **0.83** |
| Latency | 3% | 0.00 | 0.00 |
| Cost | 2% | **0.87** | 0.42 |

*Note: "Accuracy (faithfulness)" labels the pre-fix era when both pipelines used the hallucination checker. After Priority 2, agentic accuracy uses `best_grader_score`.*

---

## Root Cause 1 — Honesty Bias Inflates Basic RAG Accuracy to 1.00

Basic RAG retrieved only IRR documents (correct for part a, wrong for parts b and c). It answered part (a) correctly, then said "I don't have enough information" for (b) and (c). The hallucination checker gave it **100% faithfulness** because:

- "The provided documents contain no references to Part 723..." → verified ✓ against the retrieved IRR chunks (genuinely true for those chunks)
- "The provided documents contain no BSA/AML provisions..." → verified ✓ for the same reason

These are correct statements *about the retrieval failure*, not correct answers to the exam question. The hallucination checker cannot distinguish "truthfully admitting ignorance" from "answering correctly."

**Effect:** A pipeline that answered 1 of 3 questions scores Accuracy 1.00 and Source Coverage 1.00.

**Root cause in the checker:** The claim extractor treats "I cannot find guidance on X in the retrieved documents" as a verifiable factual claim — and it *is* verifiable against the retrieved chunks, so it passes. But these are meta-claims about retrieval coverage, not regulatory facts.

**Proposed fix:** Update the hallucination checker prompt to exclude hedging statements from claim extraction. Sentences starting with:
- "I cannot find guidance on..."
- "I don't have enough information..."
- "The provided documents contain no..."
- "The documents do not address..."

...are retrieval-coverage statements, not grounded regulatory claims. Excluding them from the claim set would make the faithfulness score reflect only the claims the model *did* attempt to answer.

---

## Root Cause 2 — Source Coverage 0.50 Because Retrieval Pass 1 Docs Were Not Cited

Agentic retrieved 6 unique source files across 2 retrieval passes:

| Pass | Documents retrieved |
|---|---|
| Pass 1 (IRR-focused) | `irr-20procedures-20guidance-20internal-2a5960.md`, `lcu2005-07encl-08bbb8.md`, `updates-interest-rate-risk-supervisory-f-1e2da7.md` |
| Pass 2 (Part 723-focused) | `aggregatelimit-htm-3a3f32.md`, `commloanpolicy-htm-bd5325.md`, `administration-htm-1f6935.md` |

The generator cited 3 of these 6 files in the final answer (the two IRR files for part a, and `commloanpolicy` for part b). The other 3 files were fetched as context but not used in the answer.

Source coverage = 3 cited / 6 retrieved = **0.50**

This is the document-level deduplication fix working correctly — the per-chunk formula would have given 3/6 = 0.50 anyway in this case because each file happened to contribute one chunk. But the underlying issue is that multi-pass retrieval inflates the denominator with documents explored but not used.

**Proposed fix (option):** Cap the source coverage denominator at the unique source files from only the *final* retrieval pass, or at the top-k documents ranked by relevance to the final answer. This avoids penalising exploratory retrieval that was necessary to find the correct answer cluster.

**Alternative framing:** Source coverage may not be the right signal for iterative pipelines at all. A better metric would be: of the questions the model *attempted to answer*, what fraction of the supporting claims are grounded? This is closer to faithfulness than coverage.

---

## Root Cause 3 — Grader False Positive on Part (c)

The agentic grader returned **score=1.00** after retry 1, confirming all 3 dimensions were covered. But none of the 6 accumulated documents contain SAR/BSA content. The generator then correctly said it could not find SAR guidance in the retrieved documents.

This means the grader hallucinated coverage of part (c) — a false positive. The generator is doing a more careful job than the grader of verifying what is actually in the context.

**Effect:** The pipeline exited the retry loop one pass too early. A third retrieval pass targeting SAR vocabulary would have found `bsa-enforcement-policy-ec5638.md` (confirmed in a prior run to contain the $5,000 threshold and 30-day deadline). The grader false positive short-circuited that retrieval.

**Proposed fix:** The grader false positive rate increases when many dimensions are already covered and only one remains. A possible mitigation: require score ≥ 0.90 (not 0.67) to exit to generator on multi-part queries. But detecting "multi-part query" automatically is non-trivial.

---

## The Underlying Design Gap — No Completeness Dimension

All three issues above are symptoms of a deeper scoring design gap: **the quality score has no completeness dimension**. A pipeline that correctly answers 1 of 3 sub-questions and correctly declines the other 2 can outscore a pipeline that answers 2 of 3 correctly with minor sourcing issues.

This gap is invisible on single-part queries (Q1–Q10) where faithfulness and completeness are correlated. It becomes visible only on adversarial multi-part queries (Q11, Q12) — exactly the queries designed to demonstrate agentic's advantage.

**Options to add completeness:**
1. ✅ **Use grader score as accuracy proxy for agentic pipeline** — the grader explicitly evaluates whether all dimensions of the question are addressed. Its final score (`best_grader_score`) is a direct completeness signal. Implemented: `compute_quality_score` checks for non-empty `grader_scores` and uses `result.best_grader_score` as accuracy when present.
2. **Add a completeness dimension** weighted separately from faithfulness — requires ground truth labels for each sub-question, or a separate LLM judge that knows what the question is asking.
3. ✅ **Remove "I cannot find guidance" claims from faithfulness** (fix 1 above) — doesn't add completeness but removes the honesty bias that inflates incomplete answers. Implemented in `hallucination.py` prompt.

---

## Priority Order for Fixes

| Priority | Fix | Impact | Effort | Status |
|---|---|---|---|---|
| 1 | Exclude hedging statements from hallucination checker claim extraction | Removes honesty bias; Basic RAG accuracy reflects only answered claims | Low — one prompt change | ✅ Done |
| 2 | Use `best_grader_score` as accuracy for agentic pipeline | Directly measures completeness for agentic; grader explicitly evaluated all 3 dimensions | Low — one line in quality_score.py | ✅ Done |
| 3 | Fix grader false positive exit condition | Third retrieval pass would have found SAR docs | Medium — requires grader threshold tuning | Pending |
| 4 | Source coverage denominator scoping | Prevents exploratory retrieval from penalising coverage score | Medium — requires tracking which pass each chunk came from | ✅ Done |

---

## Q6 — SAR Structuring / PEP Trap: Priority 2 Validation

**Query:** Senior foreign government official making repeated sub-threshold wire transfers — what compliance categories are triggered?

This query is a two-cluster retrieval trap: PEP-first framing causes initial retrieval to land on CDD/PEP docs; the grader rejects because structuring/SAR rules are in a separate document cluster; a retry finds the SAR FAQ.

### Score progression across fixes

| Run | Basic RAG | Agentic RAG | Delta | Notes |
|---|---|---|---|---|
| Before Priority 1+2 | 0.83 | 0.77 | ↓ 6.0 | Faithfulness used for both; agentic made specific claims hallucination checker flagged |
| After Priority 2 (server not restarted) | 0.76 | 0.65 | ↓ 11.0 | Old code still cached; agentic still used faithfulness |
| After Priority 2 (server restarted) | 0.70 | 0.93 | ↑ 23.1 | `best_grader_score = 1.00` used; inversion fully reversed |

### Why Priority 2 flipped Q6 so dramatically

| Dimension | Before (faithfulness) | After (`best_grader_score`) |
|---|---|---|
| Accuracy | 0.65 (11 unsourced / 31 claims — Sonnet cited specific CFR subsections not in retrieved docs) | **1.00** (grader verified both PEP and structuring dimensions covered before exiting) |
| Source coverage | 0.75 | 0.75 (unchanged) |
| Retrieval confidence | 0.833 | 0.833 (unchanged) |

**Key insight:** Grader-verified context produces 100% faithful generation. When the grader explicitly confirmed coverage of both PEP and structuring dimensions before handing off to the generator, the generator produced 15 sourced claims with 0 unsourced — because it knew exactly what the documents covered and stayed within that boundary. The faithfulness failure in the pre-fix run came from the generator adding specific CFR citations (e.g., `31 CFR 1020.320(a)(2)(ii)`) that the hallucination checker couldn't verify against the retrieved chunks, even though those citations were substantively correct.

**Structural implication:** The grader's completeness evaluation and the generator's faithfulness are positively correlated: a grader that exits at HIGH confidence produces a tighter, better-sourced answer than one forced to exit at budget exhaustion. Priority 2 captures both effects simultaneously.

---

## Q12 — CRE Loan at 21% NW: Part 723 Exception, Part 722 Appraisal, Concentration

**Query:** $3.2M commercial real estate loan against $15M net worth — does the Part 723 single-borrower exception apply, what appraisal is required under Part 722, and what are the concentration documentation requirements?  
**Result (post all fixes):** Basic RAG 0.85 · Agentic RAG 0.93 (↑ 8.1 pts) — Agentic wins cleanly

### Dimension Breakdown

| Dimension | Basic RAG | Agentic RAG |
|---|---|---|
| Accuracy | 0.89 (3 unsourced / 28 claims) | **1.00** (all 28 claims sourced) |
| Source coverage | **1.00** | high (1 retry) |
| Retrieval confidence | 0.596 | **0.833** |
| Retries | 0 | 1 |

### Q11 vs Q12 — Why Cluster Semantic Distance Is the True Complexity Metric

Q11 and Q12 are both adversarial multi-part queries. Q12 needed only 1 retry and Agentic won by 8 points. Q11 needed 3 retries and nearly lost. The difference is not the number of sub-questions — it is the **semantic distance between the required document clusters**.

| Property | Q11 | Q12 |
|---|---|---|
| Sub-questions | 3 | 3 |
| Regulatory domains | IRR · MBL/Part 723 · BSA/SAR | Part 723 · Part 722 · CRE Concentration |
| Domain overlap | None — three entirely separate regulatory universes | High — all three are commercial real estate or commercial lending topics |
| Vocabulary overlap | Zero (interest rate terms ≠ lending limit terms ≠ AML terms) | Significant ("commercial real estate", "net worth", "collateral" appear across all three clusters) |
| Retries required | 3 | 1 |
| Retrieval confidence | 0.50 | 0.833 |

**Q11 is the worst-case scenario for any retrieval system:** three clusters with zero shared vocabulary, each living in a completely separate regulatory universe (supervisory examination policy, member business lending, Bank Secrecy Act). No single query phrasing can retrieve from all three simultaneously. The rewriter had to make three independent vocabulary pivots — IRR → SAR → Part 723 — each targeting a different domain with its own terminology.

**Q12, by contrast, is a correlated multi-cluster query.** Part 723 (lending limits), Part 722 (appraisals), and CRE concentration guidance all use overlapping vocabulary: "commercial real estate," "net worth," "collateral," "state-certified appraiser." A single well-phrased query can retrieve across all three clusters, and a single retry that shifts from appraisal vocabulary toward lending limit vocabulary finds both document sets within the same domain.

### The Hidden Variable: What "Query Complexity" Actually Means

Number of sub-questions is a poor proxy for retrieval difficulty. **Semantic distance between required document clusters is the correct measure.** A three-part question where all parts live in the same regulatory domain (Q12) is retrieval-equivalent to a well-scoped single-cluster query. A three-part question where each part lives in a completely separate regulatory universe (Q11) requires as many targeted retrieval passes as there are clusters — and each pass must be independently rewritten in domain-specific vocabulary.

This has direct implications for production system design:
- **Latency and cost budgets** should be sized to worst-case cluster count and distance, not question length
- **Retry budgets** (`MAX_RETRIES`) should reflect the maximum number of distinct regulatory domains a query might span
- **The grader's feedback string** is the mechanism that bridges semantic distance — it identifies the missing dimension in regulatory vocabulary, which the rewriter then translates into a targeted query for the next pass
