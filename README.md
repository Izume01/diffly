# Diffly ⚡

**Event-driven, multi-agent AI code review platform engineered for zero-trust pull request evaluation, security vulnerability detection, and automated 1-click GitHub review comments.**

Diffly combines **FastAPI**, **Valkey** (Redis-compatible memory store), **Arq** async background workers, **Neon Serverless PostgreSQL**, and **PydanticAI** into an enterprise-grade PR review engine that outperforms conventional static and AI analysis tools.

---

## Architecture Overview

```mermaid
flowchart TD
    GH[GitHub PR Event] -->|Webhook POST| SMEE[Smee.io Dev Proxy]
    SMEE -->|Forward| API[FastAPI Webhook Handler]
    
    subgraph Ingestion & Deduplication
        API -->|HMAC-SHA256| HMAC{Valid Signature?}
        HMAC -->|No| R401[401 Unauthorized]
        HMAC -->|Yes| VALKEY[(Valkey Cache)]
        VALKEY -->|SET NX EX 86400| DEDUP{Unique Delivery?}
        DEDUP -->|Duplicate| D200[200 Duplicate Ignored]
        DEDUP -->|Acquired| QUEUE[Enqueue Job: review_pr]
    end

    subgraph Background Execution Pipeline
        QUEUE --> WORKER[Arq Background Worker]
        WORKER --> TOKENS[GitHub App RS256 JWT Auth]
        WORKER --> DIFF[Fetch Pull Request Diff]
        WORKER --> GUARD[Guardrails: Filter Lockfiles & Strip Invisible Unicode]
        
        GUARD --> AGENTS[Multi-Agent Review Pipeline]
        subgraph PydanticAI Multi-Agent Engine
            AGENTS --> S_SEC[Security Specialist]
            AGENTS --> S_PERF[Performance Specialist]
            AGENTS --> S_ARCH[Architecture Specialist]
            S_SEC & S_PERF & S_ARCH --> AGG[Judge / Aggregator Agent]
        end

        AGG --> SANITIZE[Egress Sanitizer: Strip Tracking Pixels & Exfiltration Beacons]
        SANITIZE --> POST[Post Structured Review & 1-Click Code Suggestions to PR]
        SANITIZE --> DB[(Neon Serverless PostgreSQL)]
    end

    subgraph Developer Authentication & SaaS Dashboard
        USER[Developer Browser] -->|Login with GitHub| AUTH_ROUTER[FastAPI-Users OAuth Router]
        AUTH_ROUTER -->|JWT Bearer Token| SECURE_API[Protected API Endpoints]
        SECURE_API -->|Query Repositories & Reviews| DB
    end
```

---

## Key Features & Benchmark Track Record

- **Multi-Agent Evaluation Pipeline:** Specialized agents evaluate security, performance, and architecture concurrently before a fan-in aggregator synthesizes findings into actionable GitHub 1-click suggestions.
- **Deterministic Pre-Flight Guardrails:** Strips zero-width unicode characters (`\u200B-\u200D`, `\uFEFF`) and bidi overrides to neutralize Trojan Source attacks before passing diffs to LLMs. Automatically suppresses noise by filtering out package lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `poetry.lock`).
- **Egress Exfiltration Defense:** Deterministically purges outbound HTML tags, markdown image tracking pixels, and external webhooks to stop prompt injection exfiltration attacks.
- **Live Benchmark Record (Tested on [`Izume01/test`](https://github.com/Izume01/test)):**
  - **100% recall** across adversarial benchmarks (PR #4 through #9).
  - Outperformed **Sentry Seer** and **GitGuardian** by catching unclosed file-descriptor connection leaks, compound auth bypasses, and zero-hint SSRF exploits missed by existing tools.

---

## Technology Stack

- **Runtime & Language:** Python 3.13+ managed via [`uv`](https://github.com/astral-sh/uv)
- **API Framework:** [FastAPI](https://fastapi.tiangolo.com/) with async ASGI lifespan
- **Database & Persistence:** [Neon Serverless PostgreSQL](https://neon.tech/) using [SQLModel](https://sqlmodel.tiangolo.com/) and `asyncpg`
- **Database Migrations:** [Alembic](https://alembic.sqlalchemy.org/) with asyncpg pipeline and Neon PgBouncer transaction-mode caching bypass
- **Task Queue & In-Memory State:** [Valkey](https://valkey.io/) (Aiven Cloud) + [Arq](https://github.com/samuelcolvin/arq) async worker pool
- **AI Agent Framework:** [PydanticAI](https://ai.pydantic.dev/) structured LLM agents
- **Authentication:** [FastAPI-Users](https://fastapi-users.github.io/fastapi-users/) with GitHub OAuth2 and JWT Bearer strategies

---

## Environment Configuration

Create a `.env` file in the project root:

```ini
# GitHub App Configuration
APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=/path/to/diffly-app.private-key.pem
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret

# Valkey / Redis Task Queue
VALKEY_URI=rediss://default:password@valkey-instance.aivencloud.com:port

# Neon Serverless PostgreSQL (Pooled Connection String)
DATABASE_URL=postgresql://user:password@ep-spring-sound-pooler.region.aws.neon.tech/neondb?sslmode=require

# LLM Providers (OpenAI-compatible / OpenRouter / Nara)
LLM_ENDPOINT=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=anthropic/claude-3.5-sonnet

# Authentication & GitHub OAuth (Optional for Bot, Required for Web Dashboard)
GITHUB_CLIENT_ID=Iv...
GITHUB_CLIENT_SECRET=...
AUTH_SECRET=your_random_64_char_jwt_secret_key
```

---

## Command Reference

### 1. Installation & Environment Setup

```bash
# Clone the repository
git clone https://github.com/Izume01/diffly.git
cd diffly

# Install dependencies and create virtual environment via uv
uv sync

# Install node / smee client for local development tunneling
pnpm install -g smee-client
```

---

### 2. Running the Local Development Stack

Diffly requires three background daemons running during local testing:

```bash
# Terminal 1: Start Smee Webhook Tunnel (forwards GitHub events to localhost)
smee -u https://smee.io/YOUR_SMEE_CHANNEL_ID -t http://localhost:8000/webhooks/github

# Terminal 2: Start FastAPI Webhook & API Server
uv run uvicorn diffly.main:app --port 8000 --reload

# Terminal 3: Start Arq Background Task Worker
uv run arq diffly.workers.worker.WorkerSettings
```

---

### 3. Database Migrations (Alembic)

Diffly uses Alembic configured for 100% async execution over `asyncpg` with Neon PgBouncer transaction-pooling compatibility.

```bash
# Check current database migration status
uv run alembic current

# Verify that the database schema matches SQLModel metadata (drift check)
uv run alembic check

# Generate a new migration revision after modifying models
uv run alembic revision --autogenerate -m "add_custom_user_preferences"

# Apply all pending migrations to the database
uv run alembic upgrade head

# Roll back the last applied migration
uv run alembic downgrade -1

# Stamp the database to the latest revision without applying DDL
uv run alembic stamp head
```

---

### 4. Code Quality, Formatting & Static Typing

Diffly enforces strict type checking and zero lint errors across the entire codebase.

```bash
# Run Ruff linting check across application and migrations
uv run ruff check src/diffly alembic

# Automatically fix fixable Ruff lint and import-sorting issues
uv run ruff check --fix src/diffly alembic

# Run Pyright static type checker
uv run pyright src/diffly alembic

# Run Mypy static type checker
uv run mypy src/diffly
```

---

## API Endpoints Reference

### Core Webhooks
- `POST /webhooks/github` — Verifies HMAC-SHA256 signature, deduplicates event delivery via Valkey, and enqueues PR review jobs.
- `GET /health` — Health check status probe.

### Authentication (`fastapi-users`)
- `GET /auth/github/authorize` — Generates GitHub OAuth authorization URL with CSRF protection.
- `GET /auth/github/callback` — Handles GitHub OAuth redirect, upserts user profile, and returns a JWT access token.
- `POST /auth/jwt/login` — Exchanges user credentials for a JWT token.
- `POST /auth/jwt/logout` — Terminates user session.

### Users & Repositories (Protected Endpoints)
*Require `Authorization: Bearer <JWT>` header*
- `GET /users/me` — Returns the authenticated user's profile, GitHub username, and avatar URL.
- `PATCH /users/me` — Updates user profile fields.
- `GET /repositories/me` — Lists all GitHub repositories owned or claimed by the authenticated user.
- `POST /repositories/{repo_id}/claim` — Associates an installed GitHub repository with the authenticated user account.
- `GET /reviews/me` — Lists historical PR reviews across all repositories owned by the user.

---

## Architecture Decision Records (ADRs)

Every major architectural, library, and infrastructure decision in Diffly is formally tracked in [`docs/decisions.md`](file:///home/nyx/lab/diffly/docs/decisions.md):

- **[ADR-0001](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0001-webhook-ingestion--local-development-tunneling):** Webhook Ingestion & Local Development Tunneling (Smee.io)
- **[ADR-0002](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0002-webhook-deduplication-via-valkey-atomic-locks):** Webhook Deduplication via Valkey Atomic Locks (`SET NX EX`)
- **[ADR-0003](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0003-task-queue--worker-selection-valkey--arq-vs-celery-vs-rabbitmq):** Task Queue Selection (`arq` vs Celery vs RabbitMQ)
- **[ADR-0004](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0004-github-app-authentication--api-client-via-httpx-and-pyjwt):** GitHub App Authentication via RS256 JWTs
- **[ADR-0005](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0005-multi-agent-parallel-review-pipeline-specialists--aggregator):** Multi-Agent Parallel Review Pipeline (Specialists + Aggregator)
- **[ADR-0006](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0006-ai-agent-framework-selection-pydanticai):** AI Agent Framework Selection (PydanticAI)
- **[ADR-0007](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0007-distributed-scaling-multi-tenancy--resilience-strategy):** Distributed Scaling, Multi-Tenancy & Resilience Strategy
- **[ADR-0008](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0008-context-augmentation--multi-level-codebase-awareness):** Context Augmentation & Multi-Level Codebase Awareness
- **[ADR-0009](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0009-prompt-injection-defense--false-positive-elimination-precedents--hard-exclusions):** Prompt Injection Defense & False-Positive Elimination
- **[ADR-0010](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0010-fan-in-aggregator--judge-agent--pr-review-reaction-ux):** Fan-In Aggregator / Judge Agent & PR Review Reaction UX
- **[ADR-0011](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0011-pre-flight-input-sanitization--egress-exfiltration-guardrails):** Pre-Flight Input Sanitization & Egress Exfiltration Guardrails
- **[ADR-0012](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0012-neon-serverless-postgres-persistence-via-sqlmodel--asyncpg):** Neon Serverless Postgres Persistence via SQLModel & `asyncpg`
- **[ADR-0013](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0013-user-authentication--management-via-fastapi-users-and-github-oauth):** User Authentication & Management via FastAPI-Users and GitHub OAuth
- **[ADR-0014](file:///home/nyx/lab/diffly/docs/decisions.md#adr-0014-database-schema-migrations-via-alembic-asyncpg--sqlmodel):** Database Schema Migrations via Alembic (Asyncpg & SQLModel)

---

## License

MIT License. See `LICENSE` for details.
