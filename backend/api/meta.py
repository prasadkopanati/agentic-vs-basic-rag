"""Static metadata endpoints: experiment config and preset questions."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

import config

router = APIRouter()

_QUESTIONS_FILE = Path(__file__).parent.parent / "questions.json"


@router.get("/config")
async def get_config():
    return {
        "llm_model": config.LLM_MODEL,
        "embedding_model": config.EMBEDDING_MODEL,
        "vector_db": "ChromaDB",
        "framework": "LangGraph",
        "retrieval_type": "Semantic (voyage-law-2)",
        "eval_mode": "LLM-as-Judge",
        "rag_env": config.RAG_ENV,
    }


@router.get("/questions")
async def get_questions():
    with open(_QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)
