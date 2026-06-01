"use client";
import type { ExperimentConfig } from "@/types/demo";

interface Props {
  config: ExperimentConfig | null;
}

const BADGE_COLORS: Record<string, string> = {
  "LLM Model": "border-purple/40 text-purple bg-purple/10",
  "Embedding": "border-cyan/40 text-cyan bg-cyan/10",
  "Vector DB": "border-emerald/40 text-emerald bg-emerald/10",
  "Framework": "border-amber/40 text-amber bg-amber/10",
  "Retrieval": "border-cyan/30 text-muted bg-surface",
  "Evaluation": "border-success/40 text-success bg-success/10",
};

export default function HeaderMetadata({ config }: Props) {
  const items = config
    ? [
        { label: "LLM Model", value: config.llm_model },
        { label: "Embedding", value: config.embedding_model },
        { label: "Vector DB", value: config.vector_db },
        { label: "Framework", value: config.framework },
        { label: "Retrieval", value: config.retrieval_type },
        { label: "Evaluation", value: config.eval_mode },
      ]
    : [];

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-elevated bg-bg/80 backdrop-blur-md">
      <div className="max-w-screen-xl mx-auto px-4 h-14 flex items-center gap-3 overflow-x-auto no-scrollbar">
        <span className="text-foreground font-semibold text-sm whitespace-nowrap mr-2">
          RAG Benchmark
        </span>

        {items.length === 0 ? (
          <div className="flex gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-6 w-28 rounded-full bg-elevated animate-pulse"
              />
            ))}
          </div>
        ) : (
          items.map(({ label, value }) => (
            <span
              key={label}
              className={`inline-flex items-center gap-1.5 border rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap shrink-0 ${BADGE_COLORS[label] ?? "border-elevated text-muted bg-surface"}`}
            >
              <span className="opacity-60 uppercase tracking-wide text-[10px]">
                {label}
              </span>
              {value}
            </span>
          ))
        )}
      </div>
    </header>
  );
}
