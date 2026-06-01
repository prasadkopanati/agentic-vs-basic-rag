import os
from dotenv import load_dotenv

load_dotenv()

RAG_ENV: str = os.getenv("RAG_ENV", "dev")

LLM_MODEL: str = (
    "claude-haiku-4-5-20251001" if RAG_ENV == "dev" else "claude-sonnet-4-6"
)

EMBEDDING_MODEL: str = "voyage-law-2"
CHROMA_PERSIST_DIR: str = "./chroma_db"
CHROMA_COLLECTION_NAME: str = "ncua_compliance"

CHUNK_SIZE: int = 512
CHUNK_OVERLAP: int = 100
TOP_K: int = 3
MAX_RETRIES: int = 6

# Token cost per million tokens (USD); source: Anthropic pricing
HAIKU_INPUT_COST_PER_M: float = 0.08
HAIKU_OUTPUT_COST_PER_M: float = 0.40
SONNET_INPUT_COST_PER_M: float = 3.00
SONNET_OUTPUT_COST_PER_M: float = 15.00

COST_CEILING: float = 0.10  # $0.10/query ceiling for cost dimension normalization
LATENCY_CEILING: float = 10.0  # 10s ceiling for latency dimension normalization

# Retrieval Quality Score weight profiles
WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "compliance_grade": {
        "accuracy": 0.50,
        "source_coverage": 0.30,
        "retrieval_confidence": 0.15,
        "latency": 0.03,
        "cost": 0.02,
    },
    "high_throughput": {
        "accuracy": 0.30,
        "source_coverage": 0.15,
        "retrieval_confidence": 0.10,
        "latency": 0.40,
        "cost": 0.05,
    },
    "cost_optimized": {
        "accuracy": 0.20,
        "source_coverage": 0.10,
        "retrieval_confidence": 0.05,
        "latency": 0.25,
        "cost": 0.40,
    },
}


def input_cost_per_m() -> float:
    return HAIKU_INPUT_COST_PER_M if RAG_ENV == "dev" else SONNET_INPUT_COST_PER_M


def output_cost_per_m() -> float:
    return HAIKU_OUTPUT_COST_PER_M if RAG_ENV == "dev" else SONNET_OUTPUT_COST_PER_M


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * input_cost_per_m()
        + output_tokens / 1_000_000 * output_cost_per_m()
    )
