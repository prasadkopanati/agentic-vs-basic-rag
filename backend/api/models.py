"""Pydantic request/response models for the demo API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

WeightProfile = Literal["compliance_grade", "high_throughput", "cost_optimized"]


class RunDemoRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    weight_profile: WeightProfile = "compliance_grade"


class RunDemoResponse(BaseModel):
    demo_id: str


class ChunkModel(BaseModel):
    chunk_id: str
    text: str
    source_file: str
    source_url: str
    topic: str
    cosine_similarity: float
    regulatory_facts: list[str]


class BasicRAGResultModel(BaseModel):
    query: str
    answer: str
    chunks: list[ChunkModel]
    latency_s: float
    input_tokens: int
    output_tokens: int
    retrieval_confidence: float


class AgentStepModel(BaseModel):
    node: str
    status: str
    detail: str
    score: Optional[float] = None


class AgenticRAGResultModel(BaseModel):
    query: str
    answer: str
    chunks: list[ChunkModel]
    step_log: list[AgentStepModel]
    retry_count: int
    retrieval_confidence: float
    latency_s: float
    input_tokens: int
    output_tokens: int
    grader_scores: list[float]
    best_grader_score: float


class ClaimResultModel(BaseModel):
    claim: str
    sourced: bool
    evidence_chunk_id: Optional[str] = None


class HallucinationResultModel(BaseModel):
    claims: list[ClaimResultModel]
    faithfulness_score: Optional[float] = None
    has_warning: Optional[bool] = None


class DimensionScoresModel(BaseModel):
    accuracy: float
    source_coverage: float
    retrieval_confidence: float
    latency: float
    cost: float


class QualityScoreModel(BaseModel):
    composite: float
    dimensions: DimensionScoresModel
    profile: str


class DemoResultsResponse(BaseModel):
    demo_id: str
    query: str
    weight_profile: str
    basic_rag: BasicRAGResultModel
    agentic_rag: AgenticRAGResultModel
    grounding_basic: HallucinationResultModel
    grounding_agentic: HallucinationResultModel
    score_basic: QualityScoreModel
    score_agentic: QualityScoreModel


class ExperimentConfig(BaseModel):
    llm_model: str
    embedding_model: str
    vector_db: str
    framework: str
    retrieval_type: str
    eval_mode: str
    rag_env: str


class QuestionItem(BaseModel):
    label: str
    query: str
