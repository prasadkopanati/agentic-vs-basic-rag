"use client";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import type { AgentStep, DemoStatus } from "@/types/demo";
import { CheckCircle, Circle, Loader } from "lucide-react";

type PipelinePhase = "pending" | "running" | "completed";

interface Props {
  status: DemoStatus;
  currentStage: string;
  agentSteps: AgentStep[];
  basicRAGPhase: PipelinePhase;
  agenticRAGPhase: PipelinePhase;
  hasGrounding: boolean;
  hasScoring: boolean;
}

type StepStatus = "pending" | "active" | "done";

interface TrackStep {
  key: string;
  label: string;
  caption?: string;
}

const STEPS: TrackStep[] = [
  { key: "basic_started", label: "Basic RAG" },
  { key: "agentic_started", label: "Agentic RAG" },
  { key: "grounding", label: "Grounding Check" },
  { key: "scoring", label: "Quality Scoring" },
];

export default function ProcessTracker({
  agentSteps,
  basicRAGPhase,
  agenticRAGPhase,
  hasGrounding,
  hasScoring,
}: Props) {
  const shouldReduce = useReducedMotion();
  const iterCount = agentSteps.filter((s) => s.node === "retry_counter").length;
  const latestNode = agentSteps.at(-1)?.node;

  function getStepStatus(key: string): StepStatus {
    switch (key) {
      case "basic_started":
        if (basicRAGPhase === "completed") return "done";
        if (basicRAGPhase === "running") return "active";
        return "pending";
      case "agentic_started":
        if (agenticRAGPhase === "completed") return "done";
        if (agenticRAGPhase === "running") return "active";
        return "pending";
      case "grounding":
        return hasGrounding ? "done" : agenticRAGPhase === "completed" ? "active" : "pending";
      case "scoring":
        return hasScoring ? "done" : hasGrounding ? "active" : "pending";
      default:
        return "pending";
    }
  }

  return (
    <div className="rounded-card border border-elevated bg-surface px-5 py-4">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted mb-4">
        Execution Progress
      </h2>

      {/* Main steps */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-0">
        {STEPS.map((step, i) => {
          const s = getStepStatus(step.key);
          return (
            <div key={step.key} className="flex sm:flex-col sm:flex-1 items-center gap-2 sm:gap-1">
              <div className="flex sm:flex-col items-center sm:items-center gap-2 sm:gap-1 flex-1">
                {/* Icon */}
                <div className="shrink-0">
                  {s === "done" ? (
                    <CheckCircle size={18} className="text-success" />
                  ) : s === "active" ? (
                    <motion.div
                      animate={!shouldReduce ? { rotate: 360 } : undefined}
                      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    >
                      <Loader size={18} className="text-cyan" />
                    </motion.div>
                  ) : (
                    <Circle size={18} className="text-subtle" />
                  )}
                </div>

                {/* Connector line (horizontal on desktop) */}
                {i < STEPS.length - 1 && (
                  <div className="hidden sm:block flex-1 h-px bg-elevated mx-2 mt-2 self-start" style={{ marginTop: "9px" }} />
                )}
                {i < STEPS.length - 1 && (
                  <div className="sm:hidden w-px h-3 bg-elevated self-center" />
                )}
              </div>

              {/* Label */}
              <div className="sm:text-center sm:mt-1 min-w-0">
                <p className={`text-xs font-medium ${s === "done" ? "text-success" : s === "active" ? "text-cyan" : "text-subtle"}`}>
                  {step.label}
                </p>
                {/* Sub-detail for agentic */}
                {step.key === "agentic_started" && agentSteps.length > 0 && (
                  <p className="text-[10px] text-muted mt-0.5">
                    {agenticRAGPhase === "completed"
                      ? `${iterCount} retr${iterCount === 1 ? "y" : "ies"}`
                      : `${latestNode ?? "…"}`}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Live agent step feed */}
      <AnimatePresence>
        {agentSteps.length > 0 && agenticRAGPhase !== "completed" && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 border-t border-elevated pt-3 space-y-1 overflow-hidden"
          >
            {agentSteps.slice(-4).map((step, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-[11px]"
              >
                <span className={`shrink-0 font-mono ${step.node === "grader" ? (step.score && step.score >= 0.7 ? "text-success" : "text-warning") : "text-muted"}`}>
                  [{step.node.toUpperCase().slice(0, 3)}]
                </span>
                <span className="text-muted truncate">{step.detail}</span>
                {step.score !== undefined && step.score !== null && (
                  <span className={`shrink-0 tabular-nums ${step.score >= 0.7 ? "text-success" : "text-warning"}`}>
                    {(step.score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
