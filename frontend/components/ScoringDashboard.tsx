"use client";
import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { QualityScore } from "@/types/demo";
import { formatLatency, scoreToGrade } from "@/lib/utils";

interface Props {
  basic: QualityScore;
  agentic: QualityScore;
  basicLatency: number;
  agenticLatency: number;
  agenticRetries: number;
}

function useCountUp(target: number, duration = 1200) {
  const [value, setValue] = useState(0);
  const shouldReduce = useReducedMotion();

  useEffect(() => {
    if (shouldReduce) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const raf = requestAnimationFrame(function step(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(eased * target);
      if (t < 1) requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(raf);
  }, [target, duration, shouldReduce]);

  return value;
}

function ScoreRing({
  score,
  label,
  color,
}: {
  score: number;
  label: string;
  color: string;
}) {
  const animated = useCountUp(score);
  const grade = scoreToGrade(animated);
  const pct = (animated * 100).toFixed(0);

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="relative w-24 h-24 rounded-full flex items-center justify-center"
        style={{
          background: `conic-gradient(${color} ${animated * 360}deg, #1f2937 0deg)`,
        }}
      >
        <div className="w-16 h-16 rounded-full bg-surface flex flex-col items-center justify-center">
          <span className="text-xl font-bold text-foreground tabular-nums">{pct}</span>
          <span className="text-[10px] text-muted">/ 100</span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-xs font-semibold text-foreground">{label}</p>
        <p className="text-[10px] text-muted">Grade: {grade}</p>
      </div>
    </div>
  );
}

const DIM_LABELS: Record<string, string> = {
  accuracy: "Accuracy",
  source_coverage: "Source Coverage",
  retrieval_confidence: "Retrieval",
  latency: "Latency",
  cost: "Cost",
};

function DimBar({
  label,
  basic,
  agentic,
  delta,
}: {
  label: string;
  basic: number;
  agentic: number;
  delta: number;
}) {
  return (
    <div className="grid grid-cols-[120px_1fr_1fr_60px] gap-3 items-center">
      <span className="text-xs text-muted">{label}</span>
      {/* Basic bar */}
      <div className="h-1.5 bg-elevated rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${basic * 100}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="h-full bg-blue-400/60 rounded-full"
        />
      </div>
      {/* Agentic bar */}
      <div className="h-1.5 bg-elevated rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${agentic * 100}%` }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.1 }}
          className="h-full bg-purple rounded-full"
        />
      </div>
      <span
        className={`text-xs text-right tabular-nums ${
          delta >= 0 ? "text-success" : "text-warning"
        }`}
      >
        {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(0)}
      </span>
    </div>
  );
}

export default function ScoringDashboard({
  basic,
  agentic,
  basicLatency,
  agenticLatency,
  agenticRetries,
}: Props) {
  const gap = agentic.composite - basic.composite;

  const radarData = Object.entries(DIM_LABELS).map(([key, label]) => ({
    dimension: label,
    Basic: +(basic.dimensions[key as keyof typeof basic.dimensions] * 100).toFixed(1),
    Agentic: +(agentic.dimensions[key as keyof typeof agentic.dimensions] * 100).toFixed(1),
  }));

  return (
    <div className="rounded-card border border-elevated bg-surface p-5 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">
            Retrieval Quality Score
          </h2>
          <p className="text-xs text-muted mt-1">
            Profile:{" "}
            <span className="text-foreground capitalize">
              {agentic.profile.replace(/_/g, " ")}
            </span>
          </p>
        </div>
        {/* Summary delta */}
        <div
          className={`rounded-lg px-4 py-2 text-sm font-semibold ${
            gap >= 0
              ? "bg-success/10 text-success border border-success/20"
              : "bg-warning/10 text-warning border border-warning/20"
          }`}
        >
          Agentic RAG{" "}
          {gap >= 0 ? "outperformed" : "underperformed"} by{" "}
          {Math.abs(gap * 100).toFixed(1)} pts
        </div>
      </div>

      {/* Score rings */}
      <div className="flex justify-around gap-6 flex-wrap">
        <ScoreRing
          score={basic.composite}
          label="Basic RAG"
          color="#60a5fa"
        />
        <div className="flex flex-col items-center justify-center text-muted text-2xl">
          →
        </div>
        <ScoreRing
          score={agentic.composite}
          label="Agentic RAG"
          color="#8b5cf6"
        />
      </div>

      {/* Dimension bars */}
      <div className="space-y-3">
        <div className="grid grid-cols-[120px_1fr_1fr_60px] gap-3 text-[10px] uppercase tracking-wide text-muted">
          <span>Dimension</span>
          <span>Basic RAG</span>
          <span>Agentic RAG</span>
          <span className="text-right">Δ</span>
        </div>
        {Object.entries(DIM_LABELS).map(([key, label]) => {
          const b = basic.dimensions[key as keyof typeof basic.dimensions];
          const a = agentic.dimensions[key as keyof typeof agentic.dimensions];
          return (
            <DimBar
              key={key}
              label={label}
              basic={b}
              agentic={a}
              delta={a - b}
            />
          );
        })}
      </div>

      {/* Radar chart */}
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData}>
            <PolarGrid stroke="#1f2937" />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: "#6b7280", fontSize: 10 }}
            />
            <Radar
              name="Basic RAG"
              dataKey="Basic"
              stroke="#60a5fa"
              fill="#60a5fa"
              fillOpacity={0.15}
              strokeWidth={1.5}
            />
            <Radar
              name="Agentic RAG"
              dataKey="Agentic"
              stroke="#8b5cf6"
              fill="#8b5cf6"
              fillOpacity={0.2}
              strokeWidth={1.5}
            />
            <Legend
              wrapperStyle={{ fontSize: "11px", color: "#9ca3af" }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Footnote */}
      <p className="text-[10px] text-muted">
        Basic latency: {formatLatency(basicLatency)} · Agentic latency:{" "}
        {formatLatency(agenticLatency)} (+{agenticRetries} retr
        {agenticRetries === 1 ? "y" : "ies"}) · Higher is better for all
        dimensions
      </p>
    </div>
  );
}
