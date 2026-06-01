"""Orchestrates both RAG pipelines and evaluation, emitting SSE events throughout.

Run order: Basic RAG → Agentic RAG (with per-step events) → Grounding (parallel) → Scoring.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from evaluation.hallucination import HallucinationResult, check_hallucination
from evaluation.quality_score import compute_quality_score
from pipelines.agentic_rag import (
    AgentState,
    _compute_retrieval_confidence,
    _get_graph,
)
from pipelines.basic_rag import BasicRAGResult, run_basic_rag

# ---------------------------------------------------------------------------
# In-memory run store
# ---------------------------------------------------------------------------

_runs: dict[str, dict[str, Any]] = {}


def new_run_id() -> str:
    return uuid.uuid4().hex


def get_run(demo_id: str) -> dict[str, Any] | None:
    return _runs.get(demo_id)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _serialize_chunks(chunks: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": c["chunk_id"],
            "text": c["text"],
            "source_file": c.get("source_file", ""),
            "source_url": c.get("source_url", ""),
            "topic": c.get("topic", ""),
            "cosine_similarity": c["cosine_similarity"],
            "regulatory_facts": c.get("regulatory_facts", []),
        }
        for c in chunks
    ]


def _serialize_basic(result: BasicRAGResult) -> dict:
    return {
        "query": result.query,
        "answer": result.answer,
        "chunks": _serialize_chunks(result.chunks),
        "latency_s": result.latency_s,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "retrieval_confidence": result.retrieval_confidence,
    }


def _serialize_agentic(result: dict) -> dict:
    return {**result, "chunks": _serialize_chunks(result["chunks"])}


def _serialize_hallucination(hal: HallucinationResult) -> dict:
    return {
        "claims": [
            {
                "claim": c.claim,
                "sourced": c.sourced,
                "evidence_chunk_id": c.evidence_chunk_id,
            }
            for c in hal.claims
        ],
        "faithfulness_score": hal.faithfulness_score,
        "has_warning": hal.has_warning,
    }


def _serialize_quality(qs) -> dict:
    return {
        "composite": qs.composite,
        "dimensions": {
            "accuracy": qs.dimensions.accuracy,
            "source_coverage": qs.dimensions.source_coverage,
            "retrieval_confidence": qs.dimensions.retrieval_confidence,
            "latency": qs.dimensions.latency,
            "cost": qs.dimensions.cost,
        },
        "profile": qs.profile,
    }


# ---------------------------------------------------------------------------
# Agentic pipeline (sync, called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _run_agentic_with_events(query: str, emit: Callable[[dict], None]) -> dict:
    """Stream the agentic graph, calling emit() after each node completes."""
    initial: AgentState = {
        "original_query": query,
        "rewritten_query": "",
        "retrieved_chunks": [],
        "grader_relevant": False,
        "grader_feedback": "",
        "grader_score": 0.0,
        "best_grader_score": 0.0,
        "prev_grader_score": 0.0,
        "consecutive_stable_retries": 0,
        "last_retrieval_novel_count": 0,
        "retry_count": 0,
        "answer": "",
        "step_log": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    t0 = time.perf_counter()
    graph = _get_graph()
    final_state: AgentState | None = None
    prev_step_count = 0

    for state_snapshot in graph.stream(initial, stream_mode="values"):
        final_state = state_snapshot
        step_log = state_snapshot.get("step_log", [])

        for step in step_log[prev_step_count:]:
            emit({
                "event": "agent_step",
                "data": {
                    "node": step["node"],
                    "detail": step["detail"],
                    "retry_count": state_snapshot.get("retry_count", 0),
                    "score": step.get("score"),
                },
            })
        prev_step_count = len(step_log)

    if final_state is None:
        raise RuntimeError("Agentic graph produced no output")

    latency = time.perf_counter() - t0
    grader_scores = [
        step["score"]
        for step in final_state["step_log"]
        if step.get("node") == "grader" and "score" in step
    ]

    return {
        "query": query,
        "answer": final_state["answer"],
        "chunks": final_state["retrieved_chunks"],
        "step_log": final_state["step_log"],
        "retry_count": final_state["retry_count"],
        "retrieval_confidence": _compute_retrieval_confidence(final_state["retry_count"]),
        "latency_s": latency,
        "input_tokens": final_state["input_tokens"],
        "output_tokens": final_state["output_tokens"],
        "grader_scores": grader_scores,
        "best_grader_score": final_state.get("best_grader_score", 0.0),
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


class _AgenticProxy:
    """Duck-typed wrapper so compute_quality_score can read agentic result fields."""
    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)


async def run_demo(demo_id: str, query: str, weight_profile: str) -> None:
    """Full pipeline: basic → agentic (streaming) → grounding (parallel) → scoring."""
    event_queue: asyncio.Queue[dict] = asyncio.Queue()
    _runs[demo_id] = {"queue": event_queue, "status": "running", "result": None}

    loop = asyncio.get_event_loop()

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, event)

    try:
        # ── Basic RAG ────────────────────────────────────────────────────────
        emit({"event": "basic_rag_started"})
        basic_result: BasicRAGResult = await asyncio.to_thread(run_basic_rag, query)
        basic_serialized = _serialize_basic(basic_result)
        emit({"event": "basic_rag_completed", "data": basic_serialized})

        # ── Agentic RAG ──────────────────────────────────────────────────────
        emit({"event": "agentic_started"})
        agentic_raw = await asyncio.to_thread(_run_agentic_with_events, query, emit)
        agentic_serialized = _serialize_agentic(agentic_raw)
        emit({"event": "agentic_completed", "data": agentic_serialized})

        # ── Grounding evaluation (parallel) ──────────────────────────────────
        emit({"event": "grounding_started"})
        basic_hal, agentic_hal = await asyncio.gather(
            asyncio.to_thread(
                check_hallucination,
                query,
                basic_result.answer,
                basic_result.chunks,
            ),
            asyncio.to_thread(
                check_hallucination,
                query,
                agentic_raw["answer"],
                agentic_raw["chunks"],
            ),
        )
        grounding_data = {
            "basic": _serialize_hallucination(basic_hal),
            "agentic": _serialize_hallucination(agentic_hal),
        }
        emit({"event": "grounding_completed", "data": grounding_data})

        # ── Quality scoring ───────────────────────────────────────────────────
        agentic_proxy = _AgenticProxy(agentic_raw)
        score_basic = compute_quality_score(basic_result, basic_hal, profile=weight_profile)
        score_agentic = compute_quality_score(agentic_proxy, agentic_hal, profile=weight_profile)

        scoring_data = {
            "basic": _serialize_quality(score_basic),
            "agentic": _serialize_quality(score_agentic),
        }
        emit({"event": "scoring_completed", "data": scoring_data})

        # ── Persist and signal completion ─────────────────────────────────────
        full_result = {
            "demo_id": demo_id,
            "query": query,
            "weight_profile": weight_profile,
            "basic_rag": basic_serialized,
            "agentic_rag": agentic_serialized,
            "grounding_basic": grounding_data["basic"],
            "grounding_agentic": grounding_data["agentic"],
            "score_basic": scoring_data["basic"],
            "score_agentic": scoring_data["agentic"],
        }
        _runs[demo_id]["result"] = full_result
        _runs[demo_id]["status"] = "completed"
        emit({"event": "done"})

    except Exception as exc:
        _runs[demo_id]["status"] = "error"
        emit({"event": "error", "data": {"message": str(exc)}})
        raise
