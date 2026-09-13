# Architecture Decision Records (ADRs)

This document tracks major engineering, infrastructure, and technical decisions made in **Diffly**, explaining the context, options considered, and trade-offs.

---

## Index

- [ADR-0001: Webhook Ingestion & Local Development Tunneling](#adr-0001-webhook-ingestion--local-development-tunneling)
- [ADR-0002: Webhook Deduplication via Valkey Atomic Locks](#adr-0002-webhook-deduplication-via-valkey-atomic-locks)
- [ADR-0003: Task Queue & Worker Selection (Valkey + `arq` vs Celery vs RabbitMQ)](#adr-0003-task-queue--worker-selection-valkey--arq-vs-celery-vs-rabbitmq)
- [ADR-0004: GitHub App Authentication & API Client via `httpx` and `pyjwt`](#adr-0004-github-app-authentication--api-client-via-httpx-and-pyjwt)

---

## ADR-0001: Webhook Ingestion & Local Development Tunneling

- **Date:** 2026-09-13
- **Status:** Accepted

### Context
We are building an event-driven AI PR Reviewer that receives events from GitHub webhooks. During local development, GitHub cannot post directly to `localhost`. Furthermore, incoming webhooks must be verified to prevent unauthorized payloads.

### Options Considered
1. **ngrok**: Requires account creation, authentication tokens, and free tier URL changes on every restart.
2. **Smee.io**: Free, stateless SSE proxy built specifically by GitHub for webhook testing. Generates persistent channel URLs without login.
3. **Cloud deployment for dev**: High friction, slow iteration cycle.

### Decision
- Use **FastAPI** for high-performance async webhook intake.
- Use **Smee.io** (`smee-client`) as the local dev tunnel.
- Verify every incoming request with HMAC-SHA256 (`X-Hub-Signature-256`) against `GITHUB_WEBHOOK_SECRET` before parsing payload.

---

## ADR-0002: Webhook Deduplication via Valkey Atomic Locks

- **Date:** 2026-09-13
- **Status:** Accepted

### Context
GitHub guarantees *at-least-once* webhook delivery. Retries, network timeouts, or user redeliveries can cause duplicate webhook payloads to hit the server. Running duplicate AI reviews wastes API credits and results in duplicate comments on GitHub PRs.

### Options Considered
1. **PostgreSQL Unique Constraints**: Insert delivery IDs into a SQL table.
   - *Pros:* Persistent history.
   - *Cons:* Heavy transaction overhead on high webhook bursts; requires ongoing table pruning/vacuuming.
2. **In-Memory Valkey `SET NX EX`**:
   - *Pros:* Sub-millisecond latency, zero race conditions via atomic single-command primitive, automatic TTL cleanup (24 hours).
   - *Cons:* Ephemeral (if Valkey restarts without persistence, recent keys could be lost).

### Decision
Use Valkey's atomic `SET idempotency:github:{delivery_id} "1" NX EX 86400`:
- If key was already set (`acquired is None`), immediately return HTTP `200 OK` with `{"status": "duplicate_ignored"}`.
- Returning 200 prevents GitHub from treating it as a delivery failure and retrying.

---

## ADR-0003: Task Queue & Worker Selection (Valkey + `arq` vs Celery vs RabbitMQ)

- **Date:** 2026-09-13
- **Status:** Accepted

### Context
Reviewing PR diffs with LLMs takes multiple seconds. Doing this synchronously inside the FastAPI webhook route would cause GitHub webhooks to time out (10s limit). We need an asynchronous background worker queue.

### Options Considered
1. **RabbitMQ**:
   - *Pros:* AMQP standard, advanced exchange routing, built-in consumer ACK/nack.
   - *Cons:* Only a message broker—does not provide caching or key-value storage. Introduces a second infrastructure service alongside Valkey for the MVP.
2. **Celery**:
   - *Pros:* Battle-tested Python industry standard, rich retry/monitoring ecosystem.
   - *Cons:* Historically synchronous / prefork process model; awkward integration with native `async/await` in FastAPI; heavy configuration boilerplate.
3. **`arq` (Async Redis/Valkey Queue)**:
   - *Pros:* Built by Pydantic creator for modern async Python; native `async/await`; leverages our existing Valkey instance; built-in job deduplication (`_job_id`); lightweight.
   - *Cons:* Tied to Redis/Valkey; simpler routing compared to RabbitMQ.

### Decision
Use **Valkey + `arq`** for the task queue and background worker:
- Keeps operational footprint lean (single infrastructure dependency for cache, locks, and queues).
- Native async Python matches FastAPI seamlessly.
- Connection pool managed via FastAPI `lifespan` context manager in [`src/diffly/main.py`](file:///home/nyx/lab/diffly/src/diffly/main.py).
- Worker defined with `WorkerSettings` in [`src/diffly/workers/worker.py`](file:///home/nyx/lab/diffly/src/diffly/workers/worker.py).
- Double deduplication: front-door atomic lock via `SET NX EX` plus queue-level deduplication via `_job_id=f"github:delivery:{x_github_delivery}"`.
- Normalized `valkeys://` cloud URI scheme to `rediss://` for `arq` compatibility.

---

## ADR-0004: GitHub App Authentication & API Client via `httpx` and `pyjwt`

- **Date:** 2026-09-14
- **Status:** Accepted

### Context
To review PRs, the background worker needs to call GitHub's REST API to fetch the unified diff (`Accept: application/vnd.github.v3.diff`) and changed files. GitHub Apps authenticate via an RS256-signed JWT using the App's private key (`.pem`), which is exchanged for a short-lived (1-hour) installation access token scoped to the target repository.

### Options Considered
1. **`PyGithub`**:
   - *Pros:* High-level Python wrapper with built-in `Auth.AppAuth`.
   - *Cons:* Historically synchronous and blocking (uses `requests`); awkward in native `asyncio` worker loops; heavy footprint.
2. **`githubkit`**:
   - *Pros:* Async SDK with full Pydantic v2 models.
   - *Cons:* Large dependency tree with hundreds of generated API models when we only need 2 endpoints (token exchange + diff fetching).
3. **`httpx` + `pyjwt` + `cryptography`**:
   - *Pros:* 100% native `async/await`; minimal and lightweight; direct control over raw unified diff streaming; transparent implementation of the GitHub App RS256 JWT exchange without black-box magic.
   - *Cons:* Must write our own small helper functions for token generation and API calls.

### Decision
Use **`httpx` + `pyjwt` (with `cryptography`)**:
- Clean async I/O matching FastAPI and `arq`.
- Direct access to the raw unified diff format without SDK abstraction overhead.
- Excellent portfolio/interview narrative demonstrating deep understanding of OAuth/JWT App token exchange mechanics.


