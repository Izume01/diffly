# Diffly Scale, Infrastructure & Advanced Architecture Roadmap

This document outlines the infrastructure choices, scalability guarantees, and advanced architectural patterns designed to scale **Diffly** to handle thousands of concurrent repositories, developers, and pull requests.

---

## 1. Core Infrastructure Baseline

| Component | Technology | Rationale & Configuration |
| :--- | :--- | :--- |
| **Ingress & API** | FastAPI + Uvicorn | High-throughput asynchronous HTTP intake. Verifies GitHub HMAC SHA-256 signatures and immediately returns `200 OK` in < 20ms. |
| **Cache, Locks & Broker** | Valkey (Aiven Cloud) | Sub-millisecond atomic key-value operations (`SET NX EX`) for deduplication, state tracking, and job queueing. |
| **Task Queue & Workers** | `arq` (Async Redis/Valkey Queue) | Native `asyncio` task queue. Lightweight, low overhead, with built-in job deduplication and delayed task scheduling (`_defer_by`). |
| **Relational Database** | PostgreSQL (Neon Serverless) | Durable relational storage for audit logs, deliveries, review histories, token usage, and analytics. |
| **AI Agent Layer** | PydanticAI | Strongly-typed, structured outputs using OpenAI-compatible LLM router endpoints. |

---

## 2. Fundamental Scaling & Multi-Tenant Requirements

### A. Neon Serverless Postgres Connection Pooling
- **Problem:** When dozens or hundreds of worker processes run concurrently, direct PostgreSQL connections can quickly exhaust `max_connections` on serverless Postgres.
- **Solution:** 
  - Connect exclusively through Neon's **Pooled Connection string** (PgBouncer on port `6543`).
  - Configure worker connection pools with strict bounds (e.g., `min_size=1`, `max_size=3` per worker process) via `asyncpg`.

### B. PR Debouncing & Superseding (Stale Commit Cancellation)
- **Problem:** Developers frequently push multiple rapid commits (e.g., fixing a typo 15 seconds after opening a PR). Without debouncing, the worker spawns multiple expensive review pipelines for code that is already obsolete.
- **Solution:**
  - Store the latest active commit SHA in Valkey: `pr:{repo}:{pr_number}:head = <commit_sha>`.
  - Enqueue jobs with a short debounce delay (e.g., `_defer_by=20` seconds).
  - When a worker picks up a job, it verifies whether the job's commit SHA matches the current active `HEAD`. If a newer commit arrived, the stale job is aborted immediately with zero LLM spend.

### C. Noisy Neighbor Protection (Fair Multi-Tenant Queuing)
- **Problem:** A large enterprise or monorepo pushing 50 PRs simultaneously can starve solo developers or small repos if all jobs share a naive FIFO queue.
- **Solution:**
  - Tag every job with its `installation_id`.
  - Implement round-robin worker dispatch across installations or partition into tiered queues:
    - **Fast/High-Priority:** Small diffs (< 100 lines), active webhook triggers.
    - **Standard:** Normal-sized PRs.
    - **Bulk/Low-Priority:** Automated dependency updates (Dependabot/Renovate) and large refactors.

### D. Diff Guardrails (OOM & Token Waste Protection)
- **Problem:** Pull requests touching generated code, lockfiles (`package-lock.json`, `uv.lock`), or minified assets can explode token limits and consume gigabytes of memory.
- **Solution:**
  - **Extension & Path Denylist:** Automatically filter out lockfiles, binaries, SVG/images, vendored directories, and minified bundles.
  - **Threshold Cap:** If a diff exceeds 1,500 modified lines or 20 files, skip full line-by-line review. Post a high-level summary and analyze only the top critical source files.

### E. Multi-Layer Rate Limiting
- **Problem:** Both GitHub API (5,000 requests/hour per installation) and LLM routers (TPM and RPM caps) enforce strict rate limits that return `403` or `429` under high concurrency.
- **Solution:**
  - **Valkey Distributed Semaphore:** Limit global concurrent LLM requests.
  - **Graceful Deferral:** On receiving HTTP `429` or `403` with a `Retry-After` header, use `arq`'s `_defer_by` to re-enqueue the job with exponential backoff and jitter.

---

## 3. Advanced Engineering Patterns

### 1. Two-Tier Model Cascades (Sifter $\rightarrow$ Deep Specialist)
- **Concept:** Do not send entire raw diffs to expensive high-reasoning models.
- **Workflow:**
  1. **Tier 1 (Fast Sifter):** An ultra-fast, low-cost model (e.g., Gemini Flash / Claude Haiku) scans the diff in 300ms to categorize hunks into trivial (formatting, text changes) vs. non-trivial (business logic, auth, queries, state changes).
  2. **Tier 2 (Deep Specialists):** The 4 PydanticAI specialist agents (Security, Logic, Performance, Testing) only execute on the suspicious hunks identified by Tier 1.
- **Benefit:** 60–80% cost reduction, faster response times on clean PRs.

### 2. Incremental Delta Reviews (Content-Addressable Hunk Cache)
- **Concept:** When a developer pushes commit #2 that alters only 3 lines in 1 file out of a 20-file PR, do not re-review the 19 untouched files.
- **Workflow:**
  - Compute a content hash for each diff hunk: `hash(file_path + hunk_content)`.
  - Store previous findings indexed by hunk hash in Valkey/Postgres.
  - On new commits, review only modified or net-new hunks. Carry over cached findings for unchanged hunks.

### 3. Verification Gate: AST & Syntax Linting
- **Concept:** AI reviewers lose user trust if they suggest code with syntax errors, broken indentation, or missing closing braces.
- **Workflow:**
  - Before posting any GitHub 1-click ````suggestion` code block, run the proposed replacement through a fast AST parser (e.g., Python's `ast.parse` or Tree-sitter).
  - If the suggested code fails syntax verification, downgrade it to an explanatory comment without a broken 1-click suggestion block.

### 4. Adaptive Concurrency (AIMD / Control Theory)
- **Concept:** Fixed worker concurrency breaks when external API latencies spike.
- **Workflow:**
  - Track moving p95 latency of external LLM calls.
  - Use **Additive Increase / Multiplicative Decrease (AIMD)**:
    - If p95 latency is low and error rate is 0%: incrementally increase worker capacity.
    - If latency spikes or rate-limit warnings occur: immediately throttle back concurrency by a multiplicative factor (e.g., 30%).

### 5. Circuit Breakers & Dead-Letter Queues (DLQ)
- **Concept:** Prevent cascade failures and poison-pill crashes.
- **Workflow:**
  - **Circuit Breaker:** If the LLM provider or GitHub API fails repeatedly (e.g., 5 consecutive errors), trip the circuit open to avoid hammering degraded downstream services.
  - **Dead-Letter Queue (DLQ):** Jobs failing beyond maximum retry thresholds are diverted to a dedicated DLQ queue (`arq:dlq`) and logged to Neon with error diagnostics for inspection.
