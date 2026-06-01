"use client";
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";

const FAQS: { question: string; answer: string }[] = [
  {
    question: "Why is the Agentic Score sometimes less than Basic?",
    answer:
      "The score is multi-dimensional — it captures accuracy, source coverage, retrieval confidence, latency, and cost. Agentic RAG trades latency and cost for retrieval quality assurance. When Basic RAG's cosine similarity lands high on a well-indexed query and the grader adds token overhead without triggering a retry, the agentic composite can be marginally lower. Q4 is the clearest example: the corpus simply doesn't contain the exam-schedule fact, so all 3 retrieval attempts fail the grader. The pipeline burns latency and cost with no accuracy gain — the score reflects that effort honestly.",
  },
  {
    question: "How many retries does Agentic RAG need?",
    answer:
      "The retry budget is MAX_RETRIES=2, meaning up to 3 total retrieval attempts. Most queries (Q1–Q3, Q5) resolve on the first pass — the grader accepts relevance immediately and the pipeline goes straight to the Generator. Q4 exhausts the full budget: all 3 attempts were graded LOW because the corpus simply doesn't contain the exam-schedule fact. The retry count and each rewritten query are visible in the agentic step trace.",
  },
  {
    question: "How trustworthy is the relevance grader?",
    answer:
      "The grader is a knowledge-base-grounded binary judge (same Claude model tier as the generator). It receives the rewritten query plus the retrieved chunks and returns HIGH or LOW with a reasoning trace. It is calibrated against the 5 adversarial queries used in this demo. The grader is intentionally conservative — false negatives (retrying when chunks were actually sufficient) cost a little extra latency, but false positives (generating from weak context) produce hallucinations. Conservative grading is the safer failure mode for compliance use cases.",
  },
  {
    question: "What are the 5 quality dimensions?",
    answer:
      "Accuracy — faithfulness score from an LLM-as-judge that checks each factual claim against retrieved sources. Source Coverage — ratio of cited chunks to total retrieved. Retrieval Confidence — mean cosine similarity for Basic RAG; 1 − (retries / MAX_RETRIES) for Agentic RAG. Latency — response time normalized against a 10-second ceiling. Cost — token cost normalized against a $0.10 ceiling. Dimension weights depend on the active scoring profile: Compliance-Grade prioritizes accuracy (50%) and source coverage (30%); High-Throughput prioritizes latency (40%); Cost-Optimized prioritizes cost (40%).",
  },
  {
    question: "Why does Agentic RAG take longer?",
    answer:
      "Basic RAG is a single round-trip: retrieve then generate. Agentic RAG runs at minimum 3 LLM calls: Query Rewriter → Relevance Grader → Generator. Each retry adds another Rewriter + Grader pair on top of that. Q4, which exhausted the 2-retry budget, ran ~18 seconds and consumed ~9,600 tokens — versus ~3 seconds and ~1,200 tokens for Basic RAG on the same query. The extra time is the cost of the pipeline knowing it retrieved the wrong documents and trying again.",
  },
  {
    question: "What corpus does this demo use?",
    answer:
      "~72 publicly available NCUA and FinCEN compliance documents, chunked into ~720 pieces (512 characters, 100-character overlap). Embeddings are generated with voyage-law-2, a legal-register-optimized model, and stored in ChromaDB with cosine similarity. The corpus covers credit union net worth rules, BSA/AML requirements, SAR filing obligations, vendor management guidance, and audit threshold regulations — all sourced from NCUA.gov letters to credit unions and federal regulatory guidance.",
  },
];

export default function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const toggle = (i: number) => setOpenIndex((prev) => (prev === i ? null : i));

  return (
    <div className="rounded-card border border-elevated bg-surface p-5 space-y-4">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
          Frequently Asked Questions
        </h2>
        <p className="text-xs text-muted mt-1">
          Common questions about how the benchmark works and how to interpret the scores.
        </p>
      </div>

      <div className="divide-y divide-elevated">
        {FAQS.map((faq, i) => (
          <div key={i}>
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center justify-between gap-4 py-3 text-left group"
            >
              <span className="text-sm font-medium text-foreground group-hover:text-purple transition-colors">
                {faq.question}
              </span>
              <span className="shrink-0 text-muted">
                {openIndex === i ? (
                  <ChevronUp size={15} />
                ) : (
                  <ChevronDown size={15} />
                )}
              </span>
            </button>

            <AnimatePresence initial={false}>
              {openIndex === i && (
                <motion.div
                  key="answer"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.22, ease: "easeInOut" }}
                  className="overflow-hidden"
                >
                  <p className="pb-4 text-sm text-muted leading-relaxed">
                    {faq.answer}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </div>
  );
}
