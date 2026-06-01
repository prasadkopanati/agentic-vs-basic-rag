export type WeightProfile =
  | "compliance_grade"
  | "high_throughput"
  | "cost_optimized";

export type DemoStatus = "idle" | "running" | "completed" | "error";

export interface QuestionItem {
  label: string;
  query: string;
}

export interface ExperimentConfig {
  llm_model: string;
  embedding_model: string;
  vector_db: string;
  framework: string;
  retrieval_type: string;
  eval_mode: string;
  rag_env: string;
}

export interface Chunk {
  chunk_id: string;
  text: string;
  source_file: string;
  source_url: string;
  topic: string;
  cosine_similarity: number;
  regulatory_facts: string[];
}

export interface BasicRAGResult {
  query: string;
  answer: string;
  chunks: Chunk[];
  latency_s: number;
  input_tokens: number;
  output_tokens: number;
  retrieval_confidence: number;
}

export interface AgentStep {
  node: string;
  detail: string;
  retry_count: number;
  score?: number;
}

export interface AgentStepLog {
  node: string;
  status: string;
  detail: string;
  score?: number;
}

export interface AgenticRAGResult {
  query: string;
  answer: string;
  chunks: Chunk[];
  step_log: AgentStepLog[];
  retry_count: number;
  retrieval_confidence: number;
  latency_s: number;
  input_tokens: number;
  output_tokens: number;
  grader_scores: number[];
  best_grader_score: number;
}

export interface ClaimResult {
  claim: string;
  sourced: boolean;
  evidence_chunk_id: string | null;
}

export interface HallucinationResult {
  claims: ClaimResult[];
  faithfulness_score: number | null;
  has_warning: boolean | null;
}

export interface DimensionScores {
  accuracy: number;
  source_coverage: number;
  retrieval_confidence: number;
  latency: number;
  cost: number;
}

export interface QualityScore {
  composite: number;
  dimensions: DimensionScores;
  profile: string;
}

export type DemoEvent =
  | { event: "basic_rag_started" }
  | { event: "basic_rag_completed"; data: BasicRAGResult }
  | { event: "agentic_started" }
  | { event: "agent_step"; data: AgentStep }
  | { event: "agentic_completed"; data: AgenticRAGResult }
  | { event: "grounding_started" }
  | {
      event: "grounding_completed";
      data: { basic: HallucinationResult; agentic: HallucinationResult };
    }
  | {
      event: "scoring_completed";
      data: { basic: QualityScore; agentic: QualityScore };
    }
  | { event: "done" }
  | { event: "error"; data: { message: string } }
  | { event: "heartbeat" };
