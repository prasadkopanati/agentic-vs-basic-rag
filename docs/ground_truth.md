# Ground Truth Reference Answers

Calibration reference for the hallucination checker and manual validation pass. Each answer is derived from corpus content — specific source files verified by grep. A correct system answer must cite the regulation, threshold, or requirement listed here.

---

## Q1 — HELOC Loan-to-Value Ratio

**Query:** "What's the maximum loan-to-value ratio for a HELOC?"

**Expected answer:** NCUA does not impose a single federal maximum LTV ratio for HELOCs. Instead, credit unions must establish and document their own LTV limits as part of their real estate lending policies, consistent with safe-and-sound practices. NCUA guidance emphasizes that LTV limits should reflect the institution's risk tolerance, collateral type, and local market conditions. Appraisal requirements apply to HELOCs above threshold amounts, and credit unions must manage home equity lending concentration risk.

**Must cite:** At least one of — LTV policy requirement from `managing-risks-associated-home-equity-lending-20d86b.md`, appraisal requirement from `appraisals-home-equity-loans-87cd92.md`, or concentration risk guidance from the Fair Lending Guide PDF.

**Why basic RAG fails:** No single document states "the maximum LTV is X%." A correct answer requires synthesizing that NCUA defers to institution-level policy while citing the governance and appraisal requirements. Basic RAG often fabricates a specific percentage (e.g., "80% LTV") not present in the corpus.

**Source files verified:**
- `sample_data/ncua_letters/managing-risks-associated-home-equity-lending-20d86b.md`
- `sample_data/ncua_letters/appraisals-home-equity-loans-87cd92.md`
- `sample_data/ncua_letters/home-equity-lines-credit-nearing-their-end-draw-period-54b037.md`
- `sample_data/fair-lending-guide.pdf`

---

## Q2 — BSA Obligations and FinCEN Beneficial Ownership Rules

**Query:** "How do our BSA obligations change with the new FinCEN beneficial ownership rules?"

**Expected answer:** The FinCEN Customer Due Diligence (CDD) rule requires covered financial institutions, including federally insured credit unions, to identify and verify the beneficial owners of legal entity customers — defined as natural persons owning 25% or more equity interest, plus one individual with significant managerial control. Credit unions must incorporate these requirements into their existing BSA/AML programs, update CIP procedures, and apply risk-based ongoing monitoring to legal entity accounts.

**Must cite:** The FinCEN CDD rule requirement, the 25% beneficial ownership threshold, and BSA program integration. Source must be traceable to the FinCEN/CDD-related corpus documents.

**Why basic RAG fails:** This is a cross-document query linking the general BSA program requirements (one set of docs) with the specific FinCEN CDD rule (another set). Basic RAG retrieves either BSA docs or FinCEN docs, but rarely synthesizes both correctly — or it fabricates specific implementation deadlines.

**Source files verified:**
- `sample_data/ncua_letters/agencies-release-fact-sheet-clarify-bank-secrecy-act-due-diligence-requirements--305057.md`
- `sample_data/ncua_letters/fincen-issues-exceptive-relief-bank-secrecy-act-requirement-credit-unions-59d783.md`
- `sample_data/ncua_letters/bsa-enforcement-policy-ec5638.md`
- `sample_data/ncua_letters/interagency-statement-c94a3b.md`

---

## Q3 — Capital Adequacy Requirements

**Query:** "What are current capital adequacy requirements for credit unions?"

**Expected answer:** NCUA's prompt corrective action (PCA) framework sets net worth ratio thresholds: well-capitalized requires ≥ 7% net worth ratio; adequately capitalized ≥ 6%; undercapitalized < 6%. Complex credit unions (those with total assets > $500M under the risk-based capital rule) face additional risk-weighted capital requirements beyond the basic net worth ratio. The NCUA Board's risk-based capital rule replaced the prior "complex" credit union standard to better align capital requirements with actual asset risk.

**Must cite:** The 7% well-capitalized threshold and the $500M complex credit union applicability threshold from the risk-based capital rule documents.

**Why basic RAG fails:** The corpus contains both the original PCA thresholds and the revised risk-based capital rule. Basic RAG frequently retrieves the older proposed rule documents and may cite superseded threshold amounts or conflate the general net worth requirement with the risk-based capital overlay.

**Source files verified:**
- `sample_data/ncua_letters/final-risk-based-capital-rule-report-cd7617.md`
- `sample_data/ncua_letters/risk-based-capital-faqs-df993f.md`
- `sample_data/ncua_letters/industry-webinar-material-f0f4ba.md`
- `sample_data/ncua_letters/ncua-board-proposes-complex-credit-union-leverage-ratio-b3f19d.md`

---

## Q4 — $500M Asset Threshold and Audit Requirements

**Query:** "What audit requirements change for a credit union that crosses the $500M asset threshold?"

**Expected answer:** Credit unions holding between $10M and $500M in assets may choose one of three lower-cost alternatives for their annual financial statement audit: (1) a balance sheet audit, (2) a report on examination of internal control over Call Reporting, or (3) an audit conducted per the Supervisory Committee Guide. A credit union that exceeds the $500M asset threshold no longer qualifies for these alternatives and must conduct a full financial statement audit. This is part of NCUA's broader framework of scaling regulatory requirements to credit union size and complexity.

**Must cite:** The $10M–$500M audit alternatives provision and the three specific alternatives. Source is the Fazio congressional testimony.

**Why basic RAG fails:** The $500M figure appears in the corpus only in this audit-alternatives context. A query about "crossing the $500M threshold" may retrieve the surrounding general text about regulatory scaling without surfacing the specific audit alternatives list — or basic RAG may fabricate an examination cycle change (the original query framing) that is not in the corpus.

**Source files verified (by grep):**
- `sample_data/ncua_letters/director-office-examination-and-insurance-larry-fazio-hearing-examining-regulato-9ea43a.md`
  - Confirmed text: "Credit unions holding between $10 million to $500 million in assets may choose one of three lower-cost alternatives for their annual financial statement audits: a balance sheet audit, a report on examination of internal control over Call Reporting, or an Audit per the Supervisory Committee Guide."

---

## Q5 — SAR Filing for Wire Transfer to a PEP

**Query:** "Does a wire transfer to a politically exposed person require SAR filing?"

**Expected answer:** A wire transfer to a politically exposed person (PEP) does not automatically require SAR filing, but it triggers enhanced due diligence obligations. SAR filing is required when the institution knows, suspects, or has reason to suspect that the transaction involves funds from illegal activity, is designed to evade BSA reporting requirements, lacks a lawful purpose, or involves suspicious activity totaling $5,000 or more. If the PEP transaction meets any of those SAR thresholds — for example, structuring, unusual wire patterns, or a source of funds inconsistent with the member's profile — a SAR must be filed within 30 days of detection (60 days if no suspect can be identified). The credit union's BSA/AML program must include risk-based procedures for PEP due diligence.

**Must cite:** The SAR filing threshold ($5,000), the 30-day filing deadline, and the connection to BSA suspicious activity indicators. PEP due diligence reference also expected.

**Why basic RAG fails:** This is a high-precision query where an imprecise answer is a compliance violation. Basic RAG often over-generalizes ("all PEP transactions require a SAR") or under-specifies (missing the $5,000 threshold or 30-day deadline), both of which are wrong.

**Source files verified:**
- `sample_data/ncua_letters/frequently-asked-questions-regarding-suspicious-activity-reporting-d226c4.md`
- `sample_data/ncua_letters/joint-statement-23779b.md` or `joint-statement-7707ee.md` (PEP/AML context)
- `sample_data/ncua_letters/bsa-enforcement-policy-ec5638.md`
