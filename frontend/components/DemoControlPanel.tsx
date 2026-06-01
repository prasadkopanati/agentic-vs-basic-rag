"use client";
import { useEffect, useRef, useState } from "react";
import { useDemoStore } from "@/store/demoStore";
import { useDemoRun } from "@/hooks/useDemoRun";
import type { WeightProfile } from "@/types/demo";

const PROFILES: { key: WeightProfile; label: string; caption: string; info: string }[] = [
  {
    key: "compliance_grade",
    label: "Compliance-Grade",
    caption: "Accuracy-first · 50% faithfulness weight",
    info: "Penalises hallucinations heavily and rewards source faithfulness. Best for regulatory and audit contexts where accuracy is non-negotiable.",
  },
  {
    key: "high_throughput",
    label: "High-Throughput",
    caption: "Speed-first · 40% latency weight",
    info: "Prioritises low latency over exhaustive retrieval. Suited for high-volume query environments where response time matters more than recall depth.",
  },
  {
    key: "cost_optimized",
    label: "Cost-Optimized",
    caption: "Cost-first · 40% cost weight",
    info: "Reduces token usage and retrieval depth to minimise API spend. Trades some accuracy for significantly lower cost per query.",
  },
];

export default function DemoControlPanel() {
  const store = useDemoStore();
  const { runDemo, resetDemo } = useDemoRun();
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef<number>(0);

  useEffect(() => {
    if (store.status === "running") {
      startRef.current = Date.now();
      timerRef.current = setInterval(() => {
        setElapsed((Date.now() - startRef.current) / 1000);
      }, 200);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      if (store.status === "idle") setElapsed(0);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [store.status]);

  const iterCount = store.agentSteps.filter(
    (s) => s.node === "retry_counter"
  ).length;

  const isRunning = store.status === "running";
  const canRun = !isRunning && !!store.selectedQuestion;

  return (
    <div className="rounded-card border border-elevated bg-surface p-5 space-y-5 h-full flex flex-col">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
        Benchmark Controls
      </h2>

      {/* Question selector */}
      <div className="space-y-2">
        <label
          htmlFor="question-select"
          className="text-xs font-medium text-muted uppercase tracking-wide"
        >
          Query
        </label>
        <select
          id="question-select"
          value={store.selectedQuestion}
          onChange={(e) => store.setSelectedQuestion(e.target.value)}
          disabled={isRunning}
          className="w-full rounded-input border border-elevated bg-elevated text-foreground text-sm px-3 py-2.5 appearance-none cursor-pointer focus:outline-none focus:border-cyan/60 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {store.questions.map((q) => (
            <option key={q.label} value={q.query}>
              {q.label}
            </option>
          ))}
        </select>

        {store.selectedQuestion && (
          <div className="border-l-2 border-cyan/60 bg-cyan/5 rounded-r-md pl-3 pr-3 py-2.5">
            <p className="text-sm text-foreground/60 leading-snug">
              {store.selectedQuestion}
            </p>
          </div>
        )}
      </div>

      {/* Weight profile */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted uppercase tracking-wide">
          Scoring Profile
        </p>
        <div className="space-y-1.5">
          {PROFILES.map((p) => (
            <button
              key={p.key}
              onClick={() => store.setWeightProfile(p.key)}
              disabled={isRunning}
              className={`relative w-full text-left px-3 py-2 rounded-lg border text-sm transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                store.weightProfile === p.key
                  ? "border-cyan/60 bg-cyan/10 text-cyan"
                  : "border-elevated bg-elevated text-foreground hover:border-subtle/60"
              }`}
            >
              <span className="flex items-center justify-between gap-2">
                <span className="font-medium">{p.label}</span>
                {/* Info icon + tooltip */}
                <span
                  className="group/info relative shrink-0"
                  onClick={(e) => e.stopPropagation()}
                >
                  <span className="text-muted/50 hover:text-muted text-xs leading-none select-none">ⓘ</span>
                  <span className="pointer-events-none absolute right-0 bottom-full mb-2 w-56 rounded-lg border border-subtle/30 bg-surface px-3 py-2 text-[11px] text-muted leading-relaxed shadow-lg z-50 opacity-0 group-hover/info:opacity-100 transition-opacity duration-150">
                    {p.info}
                  </span>
                </span>
              </span>
              <span className="block text-[10px] text-muted mt-0.5">
                {p.caption}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Runtime indicators */}
      {store.status !== "idle" && (
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-elevated rounded-lg px-2 py-2">
            <p className="text-[10px] text-muted uppercase tracking-wide">
              Elapsed
            </p>
            <p className="text-sm font-semibold text-foreground tabular-nums">
              {elapsed.toFixed(1)}s
            </p>
          </div>
          <div className="bg-elevated rounded-lg px-2 py-2">
            <p className="text-[10px] text-muted uppercase tracking-wide">
              Stage
            </p>
            <p className="text-xs font-medium text-cyan truncate">
              {isRunning ? "Running" : store.status}
            </p>
          </div>
          <div className="bg-elevated rounded-lg px-2 py-2">
            <p className="text-[10px] text-muted uppercase tracking-wide">
              Retries
            </p>
            <p className="text-sm font-semibold text-foreground tabular-nums">
              {iterCount}
            </p>
          </div>
        </div>
      )}

      {/* CTA — visible only before the first run */}
      {store.status === "idle" && (
        <div className="mt-auto pt-2 pb-3 text-center space-y-1">
          <p className="text-sm font-semibold text-foreground">
            Select a question to begin
          </p>
          <p className="text-[11px] text-muted leading-snug">
            Compare how Basic RAG and Agentic RAG handle complex NCUA
            compliance queries — with full execution transparency.
          </p>
          <p className="text-[11px] text-muted/60 leading-snug">
            Clicking <span className="text-cyan/80 font-medium">Run Comparison</span> runs both pipelines simultaneously and displays results side by side.
          </p>
        </div>
      )}

      {/* Action buttons */}
      <div className={`flex gap-3 pt-2 ${store.status !== "idle" ? "mt-auto" : ""}`}>
        <button
          onClick={runDemo}
          disabled={!canRun}
          className="flex-1 rounded-button bg-cyan text-bg font-semibold text-sm py-2.5 px-4 transition-all duration-150 cursor-pointer hover:bg-cyan/90 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:scale-100"
        >
          {isRunning ? (
            <span className="flex items-center justify-center gap-2">
              <span className="inline-block w-3.5 h-3.5 border-2 border-bg/30 border-t-bg rounded-full animate-spin" />
              Running…
            </span>
          ) : (
            "Run Comparison"
          )}
        </button>

        {store.status !== "idle" && (
          <button
            onClick={() => {
              resetDemo();
              setElapsed(0);
            }}
            disabled={isRunning}
            className="rounded-button border border-elevated text-muted text-sm py-2.5 px-4 transition-all duration-150 hover:border-subtle hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Reset
          </button>
        )}
      </div>

      {store.currentStage && store.status === "running" && (
        <p className="text-[11px] text-muted text-center animate-pulse">
          {store.currentStage}
        </p>
      )}
    </div>
  );
}
