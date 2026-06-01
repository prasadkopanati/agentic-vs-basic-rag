import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatLatency(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
  return `${seconds.toFixed(1)}s`;
}

export function formatCost(inputTokens: number, outputTokens: number): string {
  const cost = (inputTokens / 1_000_000) * 0.25 + (outputTokens / 1_000_000) * 1.25;
  if (cost < 0.0001) return "<$0.0001";
  return `$${cost.toFixed(4)}`;
}

export function scoreToGrade(score: number): string {
  if (score >= 0.9) return "A";
  if (score >= 0.8) return "B";
  if (score >= 0.7) return "C";
  if (score >= 0.6) return "D";
  return "F";
}

export function scoreToPercent(score: number): string {
  return `${(score * 100).toFixed(0)}%`;
}

export function nodeLabel(node: string): string {
  const labels: Record<string, string> = {
    rewriter: "Query Rewriter",
    retriever: "Retriever",
    grader: "Relevance Grader",
    retry_counter: "Retry Counter",
    generator: "Generator",
  };
  return labels[node] ?? node;
}
