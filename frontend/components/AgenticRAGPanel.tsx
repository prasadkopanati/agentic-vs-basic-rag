"use client";
import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { CheckCircle, XCircle, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { AgentStep, AgenticRAGResult } from "@/types/demo";
import { formatLatency, formatCost, nodeLabel } from "@/lib/utils";

interface Props {
  result: AgenticRAGResult | null;
  liveSteps: AgentStep[];
  isRunning: boolean;
}

interface Iteration {
  number: number;
  steps: AgentStep[];
  passed: boolean;
}

function groupIterations(steps: AgentStep[]): Iteration[] {
  const iters: Iteration[] = [];
  let current: AgentStep[] = [];
  let num = 0;

  for (const step of steps) {
    current.push(step);
    if (step.node === "retry_counter") {
      iters.push({ number: num, steps: current, passed: false });
      current = [];
      num++;
    }
  }

  if (current.length > 0) {
    const passed = current.some((s) => s.node === "generator");
    iters.push({ number: num, steps: current, passed });
  }

  return iters;
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center bg-elevated rounded-lg px-3 py-2">
      <span className="text-[10px] uppercase tracking-wide text-muted">{label}</span>
      <span className="text-sm font-semibold text-foreground tabular-nums">{value}</span>
    </div>
  );
}

function NodeIcon({ node }: { node: string }) {
  if (node === "grader") return null;
  if (node === "retry_counter") return <RefreshCw size={12} className="text-warning" />;
  if (node === "generator") return <CheckCircle size={12} className="text-success" />;
  return <div className="w-1.5 h-1.5 rounded-full bg-cyan mt-1" />;
}

function StepRow({ step }: { step: AgentStep }) {
  const isGrader = step.node === "grader";
  const graderPassed = isGrader && step.score !== undefined && step.score >= 0.7;
  const graderFailed = isGrader && step.score !== undefined && step.score < 0.7;

  return (
    <div className="flex items-start gap-2 py-1">
      <div className="mt-0.5 shrink-0">
        <NodeIcon node={step.node} />
        {isGrader &&
          (graderPassed ? (
            <CheckCircle size={12} className="text-success" />
          ) : (
            <XCircle size={12} className="text-warning" />
          ))}
      </div>
      <div className="flex-1 min-w-0">
        <span
          className={`text-[10px] font-semibold uppercase tracking-wide ${
            isGrader
              ? graderPassed
                ? "text-success"
                : "text-warning"
              : step.node === "retry_counter"
              ? "text-warning"
              : step.node === "generator"
              ? "text-success"
              : "text-cyan"
          }`}
        >
          {nodeLabel(step.node)}
        </span>
        {step.score !== undefined && step.score !== null && (
          <span
            className={`ml-2 text-[10px] tabular-nums font-mono ${
              step.score >= 0.7 ? "text-success" : "text-warning"
            }`}
          >
            {(step.score * 100).toFixed(0)}%
          </span>
        )}
        <p className="text-[11px] text-muted leading-snug truncate">{step.detail}</p>
      </div>
    </div>
  );
}

function IterationCard({
  iter,
  isLast,
}: {
  iter: Iteration;
  isLast: boolean;
}) {
  const [open, setOpen] = useState(isLast);
  const shouldReduce = useReducedMotion();

  return (
    <motion.div
      initial={!shouldReduce ? { opacity: 0, y: 8 } : undefined}
      animate={{ opacity: 1, y: 0 }}
      className={`border rounded-lg overflow-hidden ${
        iter.passed
          ? "border-success/30 bg-success/5"
          : "border-elevated bg-elevated/50"
      }`}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left"
      >
        {iter.passed ? (
          <CheckCircle size={14} className="text-success shrink-0" />
        ) : (
          <XCircle size={14} className="text-warning shrink-0" />
        )}
        <span className="text-xs font-semibold text-foreground">
          Iteration #{iter.number + 1}
        </span>
        <span
          className={`text-[10px] ml-1 ${
            iter.passed ? "text-success" : "text-warning"
          }`}
        >
          {iter.passed ? "Passed relevance check" : "Failed — retrying"}
        </span>
        <span className="ml-auto text-subtle">
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </span>
      </button>

      {open && (
        <div className="px-3 pb-2 divide-y divide-elevated/50">
          {iter.steps.map((step, i) => (
            <StepRow key={i} step={step} />
          ))}
        </div>
      )}
    </motion.div>
  );
}

export default function AgenticRAGPanel({ result, liveSteps, isRunning }: Props) {
  const iters = groupIterations(liveSteps);
  const hasContent = liveSteps.length > 0 || result !== null;

  if (!hasContent) {
    return (
      <div className="rounded-card border border-purple/20 bg-surface p-5 space-y-4 min-h-48">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-5 rounded-full bg-gradient-to-b from-purple to-cyan" />
          <h3 className="font-semibold text-foreground">Agentic RAG</h3>
          <span className="text-xs text-muted ml-auto">Iterative retrieval</span>
        </div>
        <div className="space-y-2 animate-pulse">
          <div className="h-3 bg-elevated rounded w-3/4" />
          <div className="h-3 bg-elevated rounded w-full" />
          <div className="h-3 bg-elevated rounded w-5/6" />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-card border border-purple/30 bg-surface p-5 space-y-4"
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-5 rounded-full bg-gradient-to-b from-purple to-cyan" />
        <h3 className="font-semibold text-foreground">Agentic RAG</h3>
        <span className="text-xs text-muted ml-auto">Iterative retrieval</span>
      </div>

      {/* Metrics (after complete) */}
      {result && (
        <div className="grid grid-cols-3 gap-2">
          <MetaBadge label="Latency" value={formatLatency(result.latency_s)} />
          <MetaBadge
            label="Best Score"
            value={`${(result.best_grader_score * 100).toFixed(0)}%`}
          />
          <MetaBadge
            label="Est. Cost"
            value={formatCost(result.input_tokens, result.output_tokens)}
          />
        </div>
      )}

      {/* Iteration cards */}
      <div className="space-y-2">
        <p className="text-[10px] uppercase tracking-wide text-muted font-medium">
          Execution Trace
        </p>
        <AnimatePresence>
          {iters.map((iter, i) => (
            <IterationCard
              key={`${iter.number}-${i}`}
              iter={iter}
              isLast={i === iters.length - 1}
            />
          ))}
        </AnimatePresence>

        {isRunning && (
          <div className="flex items-center gap-2 text-xs text-muted py-1 animate-pulse">
            <div className="w-2 h-2 rounded-full bg-cyan animate-ping" />
            Processing…
          </div>
        )}
      </div>

      {/* Answer */}
      {result && (
        <div className="border-t border-elevated pt-4">
          <p className="text-[10px] uppercase tracking-wide text-muted mb-2 font-medium">
            Generated Answer
          </p>
          <div className="text-sm text-foreground leading-relaxed prose prose-sm prose-invert max-w-none">
            <ReactMarkdown>{result.answer}</ReactMarkdown>
          </div>
        </div>
      )}
    </motion.div>
  );
}
