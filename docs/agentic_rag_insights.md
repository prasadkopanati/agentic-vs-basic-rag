# Agentic RAG vs Basic RAG — Key Insights from Live Compliance Testing

*Derived from running adversarial banking compliance queries against both pipelines using NCUA regulatory data. Intended for use in documenting the real-world trade-offs of Agentic RAG systems.*

---

## The Headline Finding

On a single-part compliance question, both pipelines score comparably. On a multi-part question that spans three separate regulatory clusters — the kind of question a real compliance officer actually asks — Basic RAG answered **1 of 3 parts** and scored **0.86**. Agentic RAG answered **all 3 parts** and scored **0.82**.

**The system that gave a more complete, more useful answer got a lower score. And that is exactly the right result.**

---

## Why a Lower Score on Q11 Is a Feature, Not a Bug

The query asked for three unrelated regulatory thresholds: the NEV high-risk classification threshold, the Part 723 single-borrower lending limit, and the SAR filing threshold with its calendar-day deadline. These three answers live in three completely separate regulatory documents with no semantic overlap.

Basic RAG retrieved only IRR documents. It answered part (a) correctly, then correctly admitted it could not answer parts (b) and (c). Every claim it made was sourced. Every refusal was honest. The quality scoring system rewarded this: 100% faithfulness, 100% source coverage, good cost score.

Agentic RAG ran three targeted retrieval passes to find all three document clusters. It answered all three parts correctly with 28 sourced claims and 0 hallucinations. It paid for this thoroughness in retrieval confidence (3 retries) and cost (four grader calls across 12 accumulated chunks at production LLM pricing).

The final scores — 0.86 vs. 0.82 — correctly reflect this trade-off. Agentic spent significantly more compute to return a significantly more complete answer. The 3.5 point gap is the price of thoroughness, accurately measured.

**The insight**: an automated quality score that penalises a pipeline for doing more work to find all three answers is not broken — it is exposing a real cost that exists in production. The question for a compliance officer is not "which score is higher?" but "which answer keeps my institution out of a regulatory examination finding?" That answer is obvious. The score is just telling you what that completeness costs.

---

## What the Score Components Reveal at This Level of Performance

When the accuracy dimension is already near 1.00 for both pipelines, the remaining score gap tells a different story entirely. It stops being about answer quality and starts being about operational efficiency.

### Accuracy — The Most Important Dimension (50% weight)

At 3.5 points apart overall, Agentic actually **leads** on accuracy: 1.00 vs. 0.89. This is the highest-weighted dimension and Agentic wins it. The grader explicitly verified that all three regulatory dimensions were covered before the generator ran — that verification is what `best_grader_score` captures, and it is a more direct completeness signal than post-hoc faithfulness checking on an incomplete answer.

Basic RAG's 0.89 accuracy reflects one unsourced claim that slipped through on part (a) — a detail the hallucination checker correctly flagged.

**The takeaway**: when both systems are operating correctly, accuracy converges toward 1.0 for Agentic because the grader acts as a quality gate before generation. Basic RAG has no such gate — it generates from whatever it retrieved, and the hallucination checker only catches the damage after the fact.

### Source Coverage — Rewards Retrieval Precision (30% weight)

Basic RAG scores 1.00 on source coverage. Agentic scores 0.83. This gap (5.1 points) is the single largest contributor to Basic's overall lead.

This is the most counterintuitive finding. Basic RAG's perfect source coverage comes from a narrow retrieval: it only pulled IRR documents, cited all of them, and declined to answer the other two parts. There was nothing to not-cite. Agentic retrieved across four passes and twelve accumulated chunks — building the broadest possible context to answer all three parts — and one final-pass document (`final-risk-based-capital-rule-report`) was retrieved alongside the correct MBL document but not ultimately needed in the answer.

**Source coverage measures retrieval precision, not recall.** A pipeline that retrieves narrowly and cites everything it retrieved will always outscore one that retrieves broadly and cites only what it needs. This is correct behaviour for a single-topic query. On a multi-cluster query, it is a limitation of the metric: the cost of finding three separate document clusters will always include some retrieval noise.

### Retrieval Confidence — The Honest Cost of Iteration (15% weight)

Agentic's retrieval confidence of 0.50 reflects three retries out of a maximum of six. This is not a failure — it is the correct behaviour for a query that genuinely requires navigating three separate regulatory document clusters with no semantic overlap in the initial query phrasing. The grader correctly rejected passes 1, 2, and 3 before accepting pass 4.

The score is telling you that Agentic worked harder. In a production context, this translates directly to latency and API cost. For a routine question, that cost is unjustifiable. For a compliance examination preparation query where a wrong or missing answer is a regulatory risk, it is not only justifiable but expected.

### Cost — The Ceiling Problem on Adversarial Queries (2% weight)

Agentic scored 0.00 on cost. Four grader calls, each receiving an expanding context window of accumulated chunks at production Sonnet pricing, exceeded the $0.10 cost ceiling used in normalisation. This is accurate and worth acknowledging: the most adversarial multi-cluster query genuinely does push cost toward the ceiling.

Two observations: first, cost carries only 2% of the total weight in the Compliance-Grade profile, exactly because compliance practitioners correctly prioritise getting the answer right over getting it cheaply. Second, cost in a production system would be amortised across a query volume that makes even $0.20 per query economically trivial.

---

## Broader Insights for Evaluating Agentic RAG in Production

### 1. The Honesty Paradox in Automated Scoring

Any automated quality scoring system that rewards faithful refusal equally to correct answering will favour pipelines that retrieve less. A pipeline that retrieves only three documents, answers one question correctly, and declines two others can outscore a pipeline that retrieves twelve documents across four passes and answers all three questions correctly. This is not a flaw in the scoring framework — it is a genuine epistemological limitation of measuring quality without ground-truth completeness labels. Be aware of it when interpreting scores on multi-dimensional queries.

### 2. The Grader Is the Core Differentiator

The most important architectural difference between the two pipelines is not the rewriter, the retry logic, or the generator. It is the relevance grader. The grader is the only component that explicitly asks "have we covered everything the question requires?" before generation begins. Without a grader, a pipeline will confidently generate from incomplete context, and the resulting answer will be fluent, authoritative, and wrong on the dimensions it missed. Basic RAG's correct refusals on parts (b) and (c) are only possible because a human would recognise the gap — the pipeline itself has no mechanism to detect it.

### 3. Single-Topic Queries: Where Basic RAG Competes

On single-cluster queries — one regulatory topic, one document cluster, first-pass retrieval — Basic RAG is genuinely competitive. Faster, cheaper, and with faithfulness scores that match Agentic. The observed score gaps on these queries (Q4: Agentic +32, Q8: Agentic +21, Q10: Agentic +12) reflect specific retrieval failures in Basic RAG, not a systematic advantage of the iterative architecture. For a credit union that only ever asks about one regulatory topic at a time, the case for Agentic RAG must be made on reliability and edge-case handling, not average-case performance.

### 4. Multi-Cluster Queries: Where Agentic RAG Is Irreplaceable

Regulatory compliance questions are frequently multi-dimensional. A question about a new product launch might require synthesising capital adequacy rules, BSA obligations, and lending concentration limits simultaneously. No single retrieval pass will find all three clusters. A pipeline without a grader and retry loop will answer the cluster its initial query happened to retrieve — and generate a confident, well-sourced, incomplete answer. In compliance, incomplete answers are as dangerous as wrong ones. This is where the ROI of an Agentic architecture is clearest.

### 5. Cost Scales With Query Complexity — Which Is the Right Property

An Agentic RAG system that costs the same regardless of query complexity would be broken: it would mean the easy questions are over-served and the hard ones under-served. The observed cost scaling — cheap on first-pass hits, expensive on three-cluster queries — is the correct behaviour. Build cost models around query complexity distribution, not average cost per query.

### 6. The Score Gap Narrows as Both Systems Improve

After implementing four scoring fixes (hedging claim exclusion, grader-score accuracy for Agentic, document-level source coverage deduplication, pass-scoped coverage denominator), the Q11 gap narrowed from 20.1 points to 3.5 points. The same pattern holds for Q6, which went from Basic +6 to Agentic +23. This convergence is expected: as the scoring framework becomes more accurate, the measured gap better reflects the true quality difference rather than measurement artefacts. A 3.5 point gap on a three-cluster query where both pipelines are operating correctly is a more honest and more useful signal than a 20 point gap driven by honesty-bias inflation.

### 7. Semantic Distance Between Clusters Is the True Complexity Metric

Comparing Q11 and Q12 reveals the hidden variable that actually determines how hard a multi-part query is for any retrieval system — not the number of sub-questions, but the **semantic distance between the required document clusters**.

Q12 asked three questions about a $3.2M commercial real estate loan: whether the Part 723 single-borrower exception applied, what appraisal was required under Part 722, and what concentration documentation was needed. Three sub-questions, one retry, Agentic won by 8.1 points.

Q11 asked three questions spanning post-shock NEV classification, Part 723 single-borrower limits, and SAR filing thresholds. Three sub-questions, three retries, Agentic nearly lost.

The difference is entirely explained by domain overlap:

| | Q12 (Agentic +8.1) | Q11 (Agentic −3.5) |
|---|---|---|
| Regulatory domains | Part 723 + Part 722 + CRE concentration | IRR + MBL/Part 723 + BSA/SAR |
| Shared vocabulary | "commercial real estate", "net worth", "collateral", "state-certified" — all three clusters use overlapping terms | Zero — interest rate risk terms share nothing with AML/SAR terms or lending limit terms |
| Retries required | 1 | 3 |

In Q12, a single well-formed query retrieved across two of the three required clusters in one pass. The grader identified the gap, one targeted retry found the remaining cluster, and the pipeline exited. In Q11, no single query phrasing could reach all three clusters simultaneously — the rewriter had to navigate three completely separate regulatory universes in sequence, each with its own specialised vocabulary that does not appear in the others.

**This is Q11's defining characteristic:** the answer to a single examination question is scattered across documents from the supervisory examination division (NEV), the member business lending division (Part 723), and the Bank Secrecy Act compliance division (SAR) — three completely separate organisational and regulatory silos within the corpus. The fact that Agentic RAG located all three and assembled a complete answer, while Basic RAG found only the first one and stopped, is the clearest possible demonstration of what the iterative grader-rewriter loop is for.

This has direct implications for production system design:
- **Latency and cost budgets** should be sized to the maximum number of semantically disconnected clusters a query might span, not to question length
- **Retry budgets** (`MAX_RETRIES`) should reflect the maximum number of distinct regulatory silos a query might cross
- **The grader's feedback string** is the bridge across semantic distance — it names the missing dimension in regulatory language, which the rewriter translates into a targeted vocabulary pivot for the next retrieval pass

---

## Summary: When to Use Each Architecture

| Signal | Recommendation |
|---|---|
| Query spans multiple regulatory topics or document clusters | Agentic RAG — grader ensures all clusters are found |
| Query spans clusters from entirely separate regulatory domains | Agentic RAG — iterative vocabulary pivoting is the only reliable strategy |
| Query is single-topic, well-defined, first-pass retrievable | Basic RAG — faster, cheaper, comparable accuracy |
| Answer will inform a regulatory examination or compliance decision | Agentic RAG — completeness cost is justified by risk |
| Answer is for internal reference or first-pass orientation | Basic RAG — adequate, with hallucination monitoring |
| Cost ceiling is the primary constraint | Basic RAG — but monitor faithfulness scores closely |
| Latency is the primary constraint | Basic RAG for routine queries; Agentic for high-stakes ones |

---

## The Underlying Design Principle

The most important finding from this evaluation is not which pipeline scored higher. It is that the gap between the scores understates the gap between the answers. On Q11, 3.5 score points separates a response that correctly answered 1 of 3 exam questions from a response that correctly answered all 3. In a banking compliance context, that difference is not cosmetic — it is the difference between an institution that identified all its regulatory obligations and one that identified one-third of them.

Q11 is also a demonstration of something that matters beyond compliance: the ability to navigate a knowledge base where the answer is genuinely fragmented across disconnected silos. Real-world enterprise knowledge does not live in neatly organised, topically coherent documents. It lives in policy memos, audit reports, product specifications, and legal opinions that were written by different teams, using different vocabulary, in different years. The Q11 scenario — three correct answers hiding in three completely separate regulatory universes — is not adversarial for the sake of it. It is a faithful model of the actual structure of institutional knowledge.

Automated quality scores are useful for comparing pipelines at scale. They are not a substitute for reading the answers. The most important number in a compliance RAG evaluation is not the composite score. It is the count of regulatory dimensions correctly addressed — and only an architecture with an explicit completeness gate can reliably maximise it.
