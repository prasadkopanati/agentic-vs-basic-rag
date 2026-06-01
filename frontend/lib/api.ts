import type { ExperimentConfig, QuestionItem } from "@/types/demo";

const BASE = "/api";

export async function startDemo(
  query: string,
  weightProfile: string
): Promise<{ demo_id: string }> {
  const res = await fetch(`${BASE}/demo/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, weight_profile: weightProfile }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? "Failed to start demo");
  }
  return res.json();
}

export function openDemoStream(demoId: string): EventSource {
  // Bypass the Next.js proxy for SSE — the dev proxy buffers streaming
  // responses and delivers all events at once when the stream closes.
  const streamBase = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  return new EventSource(`${streamBase}/api/demo/${demoId}/stream`);
}

export async function getExperimentConfig(): Promise<ExperimentConfig> {
  const res = await fetch(`${BASE}/config`);
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export async function getQuestions(): Promise<QuestionItem[]> {
  const res = await fetch(`${BASE}/questions`);
  if (!res.ok) throw new Error("Failed to fetch questions");
  return res.json();
}
