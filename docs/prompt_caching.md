# Prompt Caching

## Overview

Prompt caching reduces cost and latency by reusing the KV state of a prompt prefix
across API calls. When the same prefix is sent again within the TTL window, Anthropic
reads from cache instead of recomputing — at 10% of the normal input token price.

Cache writes cost 1.25× base input price. Cache reads cost 0.10× base price.
Default TTL is 5 minutes.

Minimum cacheable length (Anthropic API):
- **1,024 tokens** — Claude Sonnet 4.6 (prod mode)
- **4,096 tokens** — Claude Haiku 4.5 (dev mode)

If a prompt is below the minimum, the API processes it normally and returns no error —
so adding `cache_control` is always safe even when the threshold isn't reached.

---

## What Was Changed

Three prompts across two pipeline files were restructured from single format strings
into a **cached static system message + dynamic human message** pattern.

### Implementation pattern

```python
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content=[{
        "type": "text",
        "text": STATIC_INSTRUCTIONS,       # stable across calls
        "cache_control": {"type": "ephemeral"},
    }]),
    HumanMessage(content=dynamic_content), # changes per call
]
response = llm.invoke(messages)
```

---

## Changes by File

### `pipelines/agentic_rag.py`

#### Grader (`grader_node`) — highest ROI

The grader is called **5–6 times per multi-part query** as the retry loop accumulates
chunks. Before this change, the full grader prompt (static instructions + dynamic
query + dynamic context) was rebuilt and sent as a string on every call. The static
instructions (~800–1,000 tokens) were redundantly re-processed each time.

**Before:**
```python
_GRADER_PROMPT = """\
You are a strict completeness grader...

Question: {query}

Retrieved documents:
{context}

[~15 grading rules, output format, ...]
"""

prompt = _GRADER_PROMPT.format(query=..., context=...)
response = llm.invoke(prompt)
```

**After:**
```python
_GRADER_SYSTEM = """\
You are a strict completeness grader...
[~15 grading rules, output format, ...]
"""  # no .format() — literal { } in JSON example

messages = [
    SystemMessage(content=[{
        "type": "text",
        "text": _GRADER_SYSTEM,
        "cache_control": {"type": "ephemeral"},
    }]),
    HumanMessage(content=f"Question: {query}\n\nRetrieved documents:\n{context}"),
]
response = llm.invoke(messages)
```

The static instruction prefix (~800–1,000 tokens) is written to cache on the first
grader call and read from cache on each subsequent retry call within the same query
run. In prod (Sonnet, 1,024-token minimum), this fires consistently.

#### Generator (`generator_node`)

Same restructuring applied for consistency. The generator is called once per query,
so the main benefit is cross-query cache hits when Q1–Q12 are run in sequence within
a 5-minute Streamlit session.

---

### `pipelines/basic_rag.py`

The basic RAG pipeline has a single LLM call per query. The static system instruction
is ~60 tokens — well below the 1,024-token minimum — so no cache hits will occur in
practice. The restructuring was applied anyway for structural consistency with the
agentic pipeline and for future-proofing if the prompt is expanded.

---

## Where Caching Applies (and Where It Doesn't)

| Node | Calls per query | Static tokens | Caches in prod? | Caches in dev? |
|---|---|---|---|---|
| Grader | 5–6 | ~800–1,000 | Yes (at/above 1,024 min) | No (below 4,096 min) |
| Generator | 1 | ~100 | No (below 1,024 min) | No |
| Rewriter | 1–5 | ~150 | No | No |
| Basic RAG | 1 | ~60 | No | No |

**Why the rewriter was not changed:** Each rewriter call uses a different prompt
variant (`_REWRITER_PROMPT_INITIAL`, `_REWRITER_PROMPT_RETRY`, `_REWRITER_PROMPT_DEAD_END`)
with highly dynamic content (feedback, previous query, corpus vocabulary). The static
preamble is ~150 tokens — far below the minimum — and the content changes too much
between calls to benefit from caching.

---

## Verifying Cache Hits

To confirm caching is active, check `usage_metadata` in the response. A cache hit
produces non-zero `cache_read_input_tokens`:

```python
usage = response.usage_metadata or {}
# Standard tokens
input_tokens  = usage.get("input_tokens", 0)
output_tokens = usage.get("output_tokens", 0)
# Cache-specific (present when caching is active)
cache_write   = usage.get("cache_creation_input_tokens", 0)
cache_read    = usage.get("cache_read_input_tokens", 0)
```

The current pipelines track only `input_tokens` and `output_tokens` for the demo
quality score. Cache hit tracking can be added later if cost visibility is needed.
