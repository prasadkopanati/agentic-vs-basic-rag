"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle, AlertTriangle, HelpCircle, ChevronDown, ChevronUp } from "lucide-react";
import type { HallucinationResult } from "@/types/demo";

interface Props {
  basic: HallucinationResult;
  agentic: HallucinationResult;
}

function riskLabel(result: HallucinationResult): {
  label: string;
  color: string;
  icon: React.ReactNode;
} {
  if (result.faithfulness_score === null) {
    return {
      label: "Unavailable",
      color: "text-muted",
      icon: <HelpCircle size={14} />,
    };
  }
  if (result.has_warning) {
    return {
      label: "Hallucination Risk",
      color: "text-warning",
      icon: <AlertTriangle size={14} />,
    };
  }
  return {
    label: "Fully Grounded",
    color: "text-success",
    icon: <CheckCircle size={14} />,
  };
}

function GroundingCard({
  title,
  variant,
  result,
}: {
  title: string;
  variant: "basic" | "agentic";
  result: HallucinationResult;
}) {
  const [claimsOpen, setClaimsOpen] = useState(false);
  const risk = riskLabel(result);
  const score = result.faithfulness_score;
  const sourcedCount = result.claims.filter((c) => c.sourced).length;

  const borderClass =
    variant === "agentic"
      ? "border-purple/30"
      : "border-blue-500/20";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-card border bg-surface p-5 space-y-4 ${borderClass}`}
    >
      <div className="flex items-center gap-2">
        <div
          className={`w-1.5 h-5 rounded-full ${
            variant === "agentic"
              ? "bg-gradient-to-b from-purple to-cyan"
              : "bg-blue-500/60"
          }`}
        />
        <h4 className="font-semibold text-foreground text-sm">{title}</h4>
      </div>

      {/* Score table */}
      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col items-center bg-elevated rounded-lg px-2 py-2">
          <span className="text-[10px] uppercase tracking-wide text-muted">Groundedness</span>
          <span className="text-sm font-semibold text-foreground tabular-nums">
            {score !== null ? `${(score * 100).toFixed(0)}%` : "—"}
          </span>
        </div>
        <div className="flex flex-col items-center bg-elevated rounded-lg px-2 py-2">
          <span className="text-[10px] uppercase tracking-wide text-muted">Sourced Claims</span>
          <span className="text-sm font-semibold text-foreground tabular-nums">
            {sourcedCount}/{result.claims.length}
          </span>
        </div>
        <div className="flex flex-col items-center bg-elevated rounded-lg px-2 py-2">
          <span className="text-[10px] uppercase tracking-wide text-muted">Halluc. Risk</span>
          <span className={`text-xs font-semibold ${risk.color}`}>
            {result.has_warning === null ? "?" : result.has_warning ? "High" : "Low"}
          </span>
        </div>
      </div>

      {/* Verdict banner */}
      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium ${
          score === null
            ? "bg-subtle/10 text-muted"
            : result.has_warning
            ? "bg-warning/10 text-warning border border-warning/20"
            : "bg-success/10 text-success border border-success/20"
        }`}
      >
        <span className="shrink-0">{risk.icon}</span>
        {score === null
          ? "Grounding check was unavailable for this run."
          : result.has_warning
          ? `${result.claims.length - sourcedCount} claim(s) could not be sourced in the retrieved context.`
          : `All ${result.claims.length} claim(s) are directly supported by retrieved documents.`}
      </div>

      {/* Claims list */}
      {result.claims.length > 0 && (
        <div>
          <button
            onClick={() => setClaimsOpen((o) => !o)}
            className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
          >
            {claimsOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            Show {result.claims.length} claim
            {result.claims.length !== 1 ? "s" : ""}
          </button>

          {claimsOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              className="mt-2 space-y-2 overflow-hidden"
            >
              {result.claims.map((claim, i) => (
                <div
                  key={i}
                  className={`text-xs rounded-lg p-2.5 border ${
                    claim.sourced
                      ? "border-success/20 bg-success/5"
                      : "border-warning/20 bg-warning/5"
                  }`}
                >
                  <span
                    className={`font-semibold mr-1.5 ${
                      claim.sourced ? "text-success" : "text-warning"
                    }`}
                  >
                    {claim.sourced ? "✓" : "✗"}
                  </span>
                  <span className="text-foreground">{claim.claim}</span>
                  {claim.evidence_chunk_id && (
                    <p className="font-mono text-[10px] text-muted mt-1">
                      Source: {claim.evidence_chunk_id}
                    </p>
                  )}
                </div>
              ))}
            </motion.div>
          )}
        </div>
      )}
    </motion.div>
  );
}

export default function GroundingPanel({ basic, agentic }: Props) {
  return (
    <div className="space-y-4">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
        Grounding &amp; Hallucination Check
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <GroundingCard title="Basic RAG" variant="basic" result={basic} />
        <GroundingCard title="Agentic RAG" variant="agentic" result={agentic} />
      </div>
    </div>
  );
}
