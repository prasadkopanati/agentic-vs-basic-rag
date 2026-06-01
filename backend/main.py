"""FastAPI application entry point.

Run from repo root: uvicorn backend.main:app --reload
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.api.demo import router as demo_router
from backend.api.meta import router as meta_router

# ---------------------------------------------------------------------------
# Rate limiter (shared state; routes import this instance via app.state)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Agentic RAG Demo API",
    description="Banking compliance RAG comparison: Basic vs Agentic",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again shortly."})


_allowed_origins = list(filter(None, [
    "http://localhost:3000",
    os.getenv("ALLOWED_ORIGIN", ""),
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(demo_router, prefix="/api/demo", tags=["demo"])
app.include_router(meta_router, prefix="/api", tags=["meta"])


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}
