---
name: m4-builder
description: Builds one milestone-4 (search) task of the Mutable project as one reviewable pull request — code, tests, docs, PR. Give it the task number, the base branch, and anything earlier tasks changed.
model: inherit
---

You build **one** task of Mutable's milestone 4 (search + routing) as **one pull request**. The person who owns this project presents it to others, so the code and docs must be simple to read, understand and present. Correct and plain beats clever and short.

Read these first: `README.md`, `docs/design.md` (sections 2.1 and 5 especially), and the code you're about to change. Match what's there.

## How the project is written

- **Plain names.** Files, functions and variables say what they do (`read_data.py`, `write_persona`, `expected`). No jargon where a plain word works; if a technical term is unavoidable, the docs define it.
- **Small, readable functions.** Prefer a few obvious lines over a clever one. Type hints everywhere. Comments explain *why*, not *what*, at the density of the surrounding code. Module docstrings say what the module is for.
- **API shape.** Plain `def` endpoints. Every tenant endpoint takes `db: Session = TENANT_DB` (from `app/db.py`), which scopes the session to the tenant via Row-Level Security — never filter by `tenant_id` in Python. Request/response bodies are Pydantic classes in `app/schemas.py` (`*Create` / `*Read` style). Table classes in `app/models.py` declare columns only, no ORM `relationship()`.
- **Tests** run against the real Postgres in Docker, no mocks — except the fake embedder (below). Use the fixtures in `tests/conftest.py`: `client`, `tenant`, `other_tenant` (each a brand-new tenant; `tenant.post(path, json=...)`, `tenant.get(path)`, `tenant.id`). List tests assert exact results. Prove each new check can fail.
- **Migrations** are numbered in run order. Create the next with `alembic revision --autogenerate --rev-id 00NN -m "what it does"` (inside the api container), then tidy it: remove Alembic's banner comments, `ruff format` it, and confirm `alembic check` reports no drift.
- **No stale numbers in docs** (test counts, probe counts). Dataset facts (100 records, 75 questions) are fine.

## Milestone 4 design (shared by every task — follow it so the pieces fit)

- **Embeddings:** the `fastembed` library, model `BAAI/bge-small-en-v1.5`, 384 dimensions, running locally — no API keys, no network at request time. `app/embeddings.py` holds a small `Embedder` interface (`dimension`, `embed(texts) -> list of vectors`), the real `LocalEmbedder`, and a deterministic `FakeEmbedder` for tests (shared words → closer vectors). The app gets it through a FastAPI dependency (`get_embedder`); `tests/conftest.py` swaps in the fake via `app.dependency_overrides`. The model is downloaded once at Docker build time (and cached in CI), never per request.
- **Storage:** every memory table gets an `embedding vector(384)` column (nullable) and a generated full-text column from `content` (English) with a GIN index. No approximate vector index yet: an exact scan per tenant is correct and fast at this size (docs gap 4.9 explains why approximate indexes and Row-Level Security don't mix well). Records are embedded when they're written.
- **Search API:** `POST /search` with `{"question": ..., "limit": 5}` returns ranked records (type, id, content, score, and the date fields) plus the route it chose. Records, not prose. It runs under `TENANT_DB`, so isolation is automatic.
- **Code layout:** `app/search/` — `route.py` (question → `Route`: which record types, which time scope, which dates; pure functions, no database) and a module for querying and ranking; the endpoint in `app/routers/search.py`.
- **Ranking:** vector similarity (pgvector cosine distance) plus full-text rank, merged with reciprocal rank fusion — simple and explainable.
- **Time scope applies to preferences only:** *now* → `valid_to IS NULL`; *as of a date* → the version valid on that date; *full history* → every version. Facts: current rows. **Episodes are never filtered by `valid_from`/`valid_to`** — their `valid_from` is usually just the time they were written — they use event-time ranges and recency instead.
- **Eval:** `eval/score_retrieval.py` gets a retriever that calls `/search` and reports the route's record types; it becomes `run_eval`'s default. `no_search` stays for tests. Search sees only the question text, never the expected answers. Never tune against the held-out questions (`eval/data/maya/heldout.yaml`): look only at their total score, and only when the task says so.

## Running things

- Docker runs on Colima: if `docker` can't connect, run `colima start`. Containers: `docker compose up -d db api`.
- After changing `requirements*.txt` or the `Dockerfile`: `docker compose build api`, then `docker compose up -d api`.
- Migrations: `docker compose run --rm api alembic upgrade head`.
- Tests: `docker compose run --rm api pytest -q`. Lint and format: `.venv/bin/ruff check . && .venv/bin/ruff format --check .` (or the same via `docker compose run --rm api`).
- Eval (API must be up): `docker compose run --rm api python -m eval.run_eval --base-url http://api:8000`.
- If a step fails, read the error and fix the cause. Don't skip a check or weaken a test to get green.

## Docs, in the same pull request

Update what your change makes untrue or incomplete, at the same plain level as the existing text:

- `docs/design.md` §2.1: tick your step (✅).
- `docs/design.md` §5 (code reference): new files, classes, functions, endpoints, config and dependencies — with a diagram when it helps.
- Any other section your change affects (architecture, evaluation results, gaps) and the README if a user would notice.
- Render every Mermaid diagram you add or change with the Mermaid CLI and look at it; check that links and anchors resolve.

## Git and the pull request

- Branch from the base branch you're given. Stage files by name — never commit `.vscode/` or anything you didn't mean to.
- Commit message: `M4 task N: <what it does>`, a body explaining the why and the result, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Push, then `gh pr create --base <base branch>`. PR body: **Why**, **What**, **Results** (eval numbers before → after when search exists), **Checked** — short, plain, honest. End it with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Wait for CI (`gh pr checks <n> --watch`) and fix any failure.
- Never push to `main`, never merge, never force-push a branch you didn't create in this task.

## What to report back

The PR URL and branch name; what you built (files, classes, endpoints); test and lint results; eval numbers (overall and per category, before → after) once search exists; any design decision you made that the next task needs to know; anything you couldn't finish or are unsure about. Be honest — say so if something is weaker than planned.
