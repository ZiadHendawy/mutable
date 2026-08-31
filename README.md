# Mutable

An AI personal assistant that reliably tracks how a user's mind changes, not just what it currently knows.

## Why

**The problem:** most "AI memory" fails the same way. It either overwrites a preference when it changes, losing what used to be true, or appends every fact to a vector store with no notion of supersession, so a stale, contradicted preference can resurface as confidently as the current one. Ask most memory-enabled AI tools "what do I want right now" after you've changed your mind more than once, and the answer can't be fully trusted.

**What this does about it:** every fact, preference, and episode is typed and temporally-versioned. Preferences specifically are versioned, not silently overwritten — when one changes, the old record is closed out and explicitly linked to its replacement, so the system always has one clear current answer and can still surface the history on request. Multi-tenant and isolated from day one via Postgres Row-Level Security.

**The direction:** this is the memory layer for a full AI personal assistant — one that can eventually act on a user's behalf (milestone 12) through whatever interface fits (milestone 10) — grounded in a record of who someone is that's actually kept up to date, not guesswork. It's a useful, standalone API on its own either way.

**Status:** milestone 2 (schema + tenant-scoped ingestion) done — all three memory types have full CRUD, enforced by Postgres RLS, with a dedicated cross-tenant isolation test proving it. Search and eval harness land in milestones 3–4. See the [Roadmap](#roadmap).

## Getting started

```bash
cp .env.example .env
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up
```

- `curl localhost:8000/health` — liveness
- `curl localhost:8000/health/db` — confirms the API can reach Postgres
- `curl -X POST localhost:8000/facts -H "X-Tenant-Id: <any-uuid>" -H "Content-Type: application/json" -d '{"content": "...", "confidence": 0.9}'` — every resource endpoint requires this header; a tenant is created implicitly the first time its id is used, no signup step

Tests: `docker compose run --rm api pytest`. Lint: `docker compose run --rm api ruff check .`

## Memory types

- **Facts** — durable assertions ("lives in London"). Point lookup + embedding search on one current value.
- **Preferences** — versioned opinions ("prefers tea to coffee"). Latest-valid-wins: a query sees the current value unless it explicitly asks historically.
- **Episodes** — timestamped events ("interviewed at X, 2026-03-04"). Many can coexist for the same topic; retrieval is recency/range-weighted, not latest-wins.

No Documents type — long-form text needs chunking, a different retrieval problem. No Policies type — behavior rules are an agent concern, not something retrieved to answer a question; representable as a Preference if ever needed.

## Architecture

**Multi-tenant from the schema up.** Every table carries `tenant_id`, enforced by Postgres Row-Level Security — not an app-level `WHERE` clause. RLS makes isolation a database-enforced invariant instead of a discipline every query has to remember; one missed filter in application code is a silent data leak.

**Three typed tables**, not one polymorphic table with a JSONB payload. `memory_facts`, `memory_preferences`, `memory_episodes` share a common shape (`id`, `tenant_id`, `content`, `embedding`, `confidence`, `valid_from`, `valid_to`, `created_at`, `source`) plus type-specific columns. Typed tables keep constraints and indexes real; JSONB would hide the structure that makes the types meaningfully different.

**Temporal validity, not overwrite.** `valid_from`/`valid_to` versions every row; a superseded preference points `superseded_by` at its replacement. A memory system that overwrites in place can't answer "what did I used to believe."

**Retrieval routes before it searches.** A rule-based classifier reads the question (date expressions → episodes, "prefer/like/hate" → preferences, else facts) and produces type + time hints. Search then runs hybrid (pgvector + full-text) per hinted table, always inside the tenant's RLS boundary, and results merge by similarity + recency + confidence. An LLM-based router is a natural v2 — deferred because it adds latency, cost, and non-determinism to every query; the eval harness can A/B it against this baseline later.

**Confidence is caller-supplied**, not inferred — there's one source per fact until an extraction pipeline exists. Ingestion is structured JSON only, no free-text extraction, so writes stay deterministic and auditable.

## Eval contract

Two synthetic tenants, no real user data in the repo. Tenant A carries the full seed set (~100 records, ~75 labeled questions) for retrieval quality. Tenant B is a minimal second tenant that exists only to probe isolation.

| Metric | Bar |
|---|---|
| Recall@5 / MRR | ≥ 0.9 / ≥ 0.8 on Tenant A |
| Cross-tenant leaks | 0, always — pass/fail, not a threshold |
| Routing accuracy | scored independently of retrieval quality |
| p95 latency | tracked from the caching milestone on |

The harness runs both suites against a live API and prints a metrics table with per-question failure diffs. It gates every PR — not an afterthought.

## Roadmap

Each milestone ships something runnable and checkable on its own — none depends on a later one to be demoable.

### 1. Scaffold
**Ships:** Docker Compose running Postgres with pgvector enabled, a migration tool wired up, CI running lint and tests on every push.
**Done when:** `docker compose up` gives a working local Postgres+pgvector; an empty migration and empty test suite both go green in CI.

### 2. Schema + tenant-scoped ingestion
**Ships:** the three typed tables (`memory_facts`, `memory_preferences`, `memory_episodes`) with `tenant_id` and RLS policies from the first migration, plus a CRUD API per type with versioning on write.
**Done when:** two tenants are seeded through the API, and a direct Postgres session for one tenant provably cannot read the other's rows.

### 3. Eval dataset & harness v1
**Ships:** synthetic seed data for two tenants — Tenant A (~100 records across facts/preferences/episodes, ~75 hand-labeled questions with gold record IDs) and Tenant B (~20–30 records, isolation probes only) — seeded through milestone 2's API; a CLI harness that runs both suites against the live API and prints a metrics table with per-question failure diffs. The gold question set gives first-class coverage to preference evolution specifically, the product's core differentiator: a "current preference" question must exclude a superseded record, and a historical question must still retrieve the old one correctly.
**Done when:** the harness runs end-to-end and reports zero cross-tenant leaks (proving milestone 2's RLS in practice) and correct supersede handling on every preference-evolution question, even though overall Recall/MRR are near-zero, since there's no search yet, only CRUD, and retrieval metrics are expected to fail until milestone 4 makes them pass.

### 4. Search + routing
**Ships:** the embedding write path, hybrid (vector + full-text) search per type, the rule-based query router — wired into the same harness from milestone 3.
**Done when:** re-running that harness now shows Recall@5 ≥ 0.9 / MRR ≥ 0.8 on Tenant A, with isolation still at zero leaks.

### 5. Caching
**Ships:** a Redis-backed embedding cache and hot-query cache, keyed per tenant.
**Done when:** the eval harness shows a measured p95 latency drop with identical Recall/MRR/isolation results — proof the cache is invisible to correctness.

### 6. Deploy + CI/CD
**Ships:** the same `docker-compose.yml` from milestone 1, deployed to a single AWS EC2 instance (not ECS/RDS — cheapest option, and the closest match to local dev, at the cost of self-managed Postgres backups instead of RDS's); CI/CD running the full eval harness (isolation gate included) as a required check before deploy.
**Done when:** there's a live endpoint on a public IP/DNS name, and a PR that breaks tenant scoping gets blocked by a red eval run before it can merge.

### 7. Accounts & billing
**Ships:** real signup/login replacing the caller-supplied opaque tenant ID, API-key issuance, basic plan gating.
**Done when:** a new tenant signs up through a real auth flow and gets a scoped key that RLS enforces exactly as it does today.

### 8. Free-text ingestion
**Ships:** an endpoint that accepts raw text and calls an LLM to extract structured facts/preferences/episodes into the existing schema.
**Done when:** pasting an unstructured paragraph produces the same typed, versioned rows a structured POST would, with extraction confidence populated and reviewable before commit.

### 9. Answer synthesis (RAG)
**Ships:** an optional endpoint that takes retrieved records and generates a prose answer via an LLM, on top of (not instead of) the existing retrieval endpoint.
**Done when:** a question returns a synthesized answer that cites the specific record IDs it drew from.

### 10. Client layer
**Ships:** a thin UI or chat interface consuming the existing API — the first real product surface on top of the engine.
**Done when:** someone who isn't you can add and query memories without touching curl or Postman.

### 11. Document/vault ingestion
**Ships:** chunked ingestion for long-form text, likely a new memory type with its own retrieval strategy.
**Done when:** a full document can be ingested and a question against it returns the right chunk, evaluated against its own gold set.

### 12. Autonomous agent behavior
**Ships:** a policy layer letting an agent act on stored memory (schedule, notify, decide), not just retrieve it.
**Done when:** an agent takes a real action informed by a memory lookup, with an audit trail of which memory drove which action.
