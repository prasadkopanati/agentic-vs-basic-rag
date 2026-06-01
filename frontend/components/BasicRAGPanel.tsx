"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { BasicRAGResult } from "@/types/demo";
import { formatLatency, formatCost } from "@/lib/utils";

interface Props {
  result: BasicRAGResult | null;
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center bg-elevated rounded-lg px-3 py-2 min-w-0">
      <span className="text-[10px] uppercase tracking-wide text-muted">{label}</span>
      <span className="text-sm font-semibold text-foreground tabular-nums">{value}</span>
    </div>
  );
}

export default function BasicRAGPanel({ result }: Props) {
  const [chunksOpen, setChunksOpen] = useState(false);

  if (!result) {
    return (
      <div className="rounded-card border border-elevated bg-surface p-5 space-y-4 min-h-48">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-5 rounded-full bg-blue-500/60" />
          <h3 className="font-semibold text-foreground">Basic RAG</h3>
          <span className="text-xs text-muted ml-auto">Single-shot retrieval</span>
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
      className="rounded-card border border-blue-500/20 bg-surface p-5 space-y-4"
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-5 rounded-full bg-blue-500/60" />
        <h3 className="font-semibold text-foreground">Basic RAG</h3>
        <span className="text-xs text-muted ml-auto">Single-shot retrieval</span>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-2">
        <MetaBadge label="Latency" value={formatLatency(result.latency_s)} />
        <MetaBadge
          label="Confidence"
          value={`${(result.retrieval_confidence * 100).toFixed(0)}%`}
        />
        <MetaBadge
          label="Est. Cost"
          value={formatCost(result.input_tokens, result.output_tokens)}
        />
      </div>

      {/* Retrieved chunks */}
      <div>
        <button
          onClick={() => setChunksOpen((o) => !o)}
          className="flex items-center gap-2 text-xs font-medium text-muted hover:text-foreground transition-colors w-full text-left"
        >
          {chunksOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {result.chunks.length} retrieved chunk
          {result.chunks.length !== 1 ? "s" : ""}
        </button>

        {chunksOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            className="mt-2 space-y-2 overflow-hidden"
          >
            {result.chunks.map((chunk, i) => (
              <div
                key={chunk.chunk_id}
                className="bg-elevated rounded-lg p-3 border border-border"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-mono text-cyan">#{i + 1}</span>
                  <span className="text-[10px] text-muted truncate flex-1">
                    {chunk.source_file}
                  </span>
                  <span className="text-[10px] tabular-nums text-muted">
                    {(chunk.cosine_similarity * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-xs font-mono text-foreground/80 leading-relaxed line-clamp-4">
                  {chunk.text}
                </p>
              </div>
            ))}
          </motion.div>
        )}
      </div>

      {/* Answer */}
      <div className="border-t border-elevated pt-4">
        <p className="text-[10px] uppercase tracking-wide text-muted mb-2 font-medium">
          Generated Answer
        </p>
        <div className="text-sm text-foreground leading-relaxed prose prose-sm prose-invert max-w-none">
          <ReactMarkdown>{result.answer}</ReactMarkdown>
        </div>
      </div>
    </motion.div>
  );
}
