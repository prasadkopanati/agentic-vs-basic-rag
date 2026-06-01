"use client";
import { create } from "zustand";
import type {
  AgentStep,
  AgenticRAGResult,
  BasicRAGResult,
  DemoEvent,
  DemoStatus,
  ExperimentConfig,
  HallucinationResult,
  QualityScore,
  QuestionItem,
  WeightProfile,
} from "@/types/demo";

const STAGE_LABELS: Record<string, string> = {
  basic_rag_started: "Running Basic RAG retrieval…",
  basic_rag_completed: "Basic RAG complete",
  agentic_started: "Starting Agentic RAG…",
  agent_step: "Agentic RAG running…",
  agentic_completed: "Agentic RAG complete",
  grounding_started: "Evaluating document grounding…",
  grounding_completed: "Grounding evaluation complete",
  scoring_completed: "Computing final comparative scores…",
  done: "Complete",
  error: "Error",
};

type PipelinePhase = "pending" | "running" | "completed";

interface DemoStore {
  selectedQuestion: string;
  weightProfile: WeightProfile;
  questions: QuestionItem[];
  experimentConfig: ExperimentConfig | null;

  demoId: string | null;
  status: DemoStatus;
  currentStage: string;
  error: string | null;

  basicRAGPhase: PipelinePhase;
  agenticRAGPhase: PipelinePhase;

  agentSteps: AgentStep[];

  basicRAGResult: BasicRAGResult | null;
  agenticRAGResult: AgenticRAGResult | null;
  groundingBasic: HallucinationResult | null;
  groundingAgentic: HallucinationResult | null;
  scoreBasic: QualityScore | null;
  scoreAgentic: QualityScore | null;

  setSelectedQuestion: (q: string) => void;
  setWeightProfile: (p: WeightProfile) => void;
  setQuestions: (qs: QuestionItem[]) => void;
  setExperimentConfig: (c: ExperimentConfig) => void;
  setDemoId: (id: string) => void;
  setStatus: (s: DemoStatus) => void;
  setError: (msg: string) => void;
  handleDemoEvent: (event: DemoEvent) => void;
  resetDemo: () => void;
}

export const useDemoStore = create<DemoStore>((set) => ({
  selectedQuestion: "",
  weightProfile: "compliance_grade",
  questions: [],
  experimentConfig: null,
  demoId: null,
  status: "idle",
  currentStage: "",
  error: null,
  basicRAGPhase: "pending",
  agenticRAGPhase: "pending",
  agentSteps: [],
  basicRAGResult: null,
  agenticRAGResult: null,
  groundingBasic: null,
  groundingAgentic: null,
  scoreBasic: null,
  scoreAgentic: null,

  setSelectedQuestion: (q) => set({ selectedQuestion: q }),
  setWeightProfile: (p) => set({ weightProfile: p }),
  setQuestions: (qs) => set({ questions: qs }),
  setExperimentConfig: (c) => set({ experimentConfig: c }),
  setDemoId: (id) => set({ demoId: id }),
  setStatus: (s) => set({ status: s }),
  setError: (msg) => set({ error: msg, status: "error" }),

  handleDemoEvent: (event) => {
    const label = STAGE_LABELS[event.event] ?? event.event;
    set({ currentStage: label });

    switch (event.event) {
      case "basic_rag_started":
        set({ basicRAGPhase: "running" });
        break;
      case "basic_rag_completed":
        set({ basicRAGResult: event.data, basicRAGPhase: "completed" });
        break;
      case "agentic_started":
        set({ agenticRAGPhase: "running" });
        break;
      case "agent_step":
        set((s) => ({ agentSteps: [...s.agentSteps, event.data] }));
        break;
      case "agentic_completed":
        set({ agenticRAGResult: event.data, agenticRAGPhase: "completed" });
        break;
      case "grounding_completed":
        set({
          groundingBasic: event.data.basic,
          groundingAgentic: event.data.agentic,
        });
        break;
      case "scoring_completed":
        set({
          scoreBasic: event.data.basic,
          scoreAgentic: event.data.agentic,
        });
        break;
      case "done":
        set({ status: "completed" });
        break;
      case "error":
        set({ status: "error", error: event.data?.message ?? "Unknown error" });
        break;
    }
  },

  resetDemo: () =>
    set({
      demoId: null,
      status: "idle",
      currentStage: "",
      error: null,
      basicRAGPhase: "pending",
      agenticRAGPhase: "pending",
      agentSteps: [],
      basicRAGResult: null,
      agenticRAGResult: null,
      groundingBasic: null,
      groundingAgentic: null,
      scoreBasic: null,
      scoreAgentic: null,
    }),
}));
