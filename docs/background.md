# Agentic RAG

## Background

Large language models are powerful reasoners, but they are fundamentally limited by what they know at training time. As the world changes, as organizations accumulate proprietary knowledge, and as queries grow more specific, a model's parametric memory is no longer enough. Retrieval-Augmented Generation (RAG) was introduced to address this — connecting a model to an external knowledge source so that answers are grounded in retrieved facts rather than baked-in weights.

Classic RAG, however, operates as a single-shot pipeline: a user query goes in, a retriever fetches the top-k documents, and the model generates a response. This works well for simple, well-formed questions. For complex, ambiguous, or poorly phrased queries it routinely fails — returning irrelevant documents, missing the point of the question, or generating a hallucinated answer dressed up in retrieved text.

## The Problem

Single-shot RAG breaks down in several predictable ways:

- **Poor query quality.** Users rarely phrase questions in a way that maximizes semantic similarity to the relevant documents. The query and the knowledge base speak different vocabularies.
- **No quality signal.** The pipeline has no mechanism to evaluate whether what was retrieved is actually relevant to the question. It blindly passes everything to the generator.
- **No recovery path.** If retrieval fails, the system has no way to detect this and try again. A bad retrieval silently produces a bad answer.
- **One chance to get it right.** The entire accuracy of the system rests on a single retrieval pass. There is no iteration, no refinement, no learning within the request.

The result is a system that is fragile at the boundaries of its knowledge and opaque about its own failures.

## The Solution: Agentic RAG

Agentic RAG replaces the single-shot pipeline with a multi-agent loop. Each agent has a narrow, well-defined responsibility. Together they form an iterative retrieval process that self-corrects until the retrieved information is genuinely relevant — or until it has exhausted its retry budget and falls back gracefully.

The core insight is that **retrieval is not a one-time event but a conversation between agents**. The system evaluates its own output, identifies when retrieval has fallen short, and rewrites its approach before trying again.

## Agents

### Query Rewriter
The first agent receives the raw user question and rewrites it into a semantically richer, more precise query before any retrieval takes place. Rather than sending the user's words directly to the knowledge base, the rewriter optimizes the query for maximum retrieval relevance — expanding vocabulary, sharpening specificity, and removing ambiguity. This single step significantly increases the likelihood that the retriever surfaces the right documents on the first pass.

### Retriever
The retriever takes the rewritten query and fetches the most semantically relevant documents from the knowledge base. It operates on meaning, not keywords — finding documents that are conceptually close to the query even when the exact words differ.

### Relevance Grader
Once documents are retrieved, the grader evaluates whether they actually answer the question. It acts as a quality gate between retrieval and generation, preventing irrelevant or tangential documents from reaching the final answer stage. Rather than assuming that retrieved equals relevant, the grader makes an explicit judgment: are these documents worth generating from?

### Decision Router
The router reads the grader's verdict and decides what happens next. If the retrieved documents are relevant, it forwards them to the generator. If they are not — and the retry budget has not been exhausted — it routes back to the rewriter to try again with a different query. This is the mechanism that makes the pipeline iterative rather than linear.

### Retry Counter
The retry counter tracks how many retrieval attempts have been made. It enforces the retry budget, ensuring the system does not loop indefinitely. When the budget is exhausted, it signals the router to proceed to generation regardless — a graceful degradation that always produces an answer rather than hanging.

### Generator
The generator produces the final response. It receives the user's original question alongside the retrieved context and synthesizes a grounded, coherent answer. Because it only runs after the grader has confirmed document relevance (or the retry budget is spent), the generator is working with the best available information the system could find.

## How It Works Together

```
User Question
      │
      ▼
  Rewriter  ◄──────────────────────┐
      │                            │
      ▼                            │
  Retriever                    Retry Counter
      │                            │
      ▼                            │
   Grader                          │
      │                            │
      ▼                            │
  Decision ── not relevant ────────┘
      │
   relevant (or retry limit reached)
      │
      ▼
  Generator
      │
      ▼
   Answer
```

Each cycle through the loop is a complete retrieval attempt. The system exits the loop when it has found relevant documents or when it determines that further retries are unlikely to improve the result. The final answer is always grounded in the best retrieval the system was able to achieve.

## Why This Matters

The shift from single-shot to iterative retrieval changes the reliability profile of the system. Errors that were previously silent and unrecoverable — a missed retrieval, a poorly phrased query — become detectable and correctable within the same request. The system is no longer dependent on getting everything right on the first try. It reasons about its own output, adjusts its approach, and converges on an accurate answer through iteration.

This is the foundation of a production-grade RAG system: not a pipeline that hopes for the best, but an agent loop that actively works toward retrieval accuracy.
