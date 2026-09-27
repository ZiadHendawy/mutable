# Mutable

An AI personal assistant that reliably tracks how a user's mind changes, not just what it currently knows.

## Why

Preferences change over time, and a memory system needs to handle that without losing history or confusing old state with current state. Every fact, preference, and episode here is typed and temporally-versioned: preferences are versioned, not overwritten, so when one changes, the old record is closed out and explicitly linked to its replacement. There's always exactly one current answer, and the full history stays queryable on request. The eval harness scores this directly, not just generic retrieval quality: a "current preference" question must exclude a superseded record, and a historical question must still retrieve the old one correctly.

Multi-tenant and isolated from day one, via Postgres Row-Level Security enforced as a database invariant rather than an application-level filter.

**The direction:** this is the memory layer for a full AI personal assistant — one that can eventually act on a user's behalf (milestone 12) through whatever interface fits (milestone 10) — grounded in a record of who someone is that's actually kept up to date, not guesswork. It's a useful, standalone API on its own either way.

**Status:** milestone 3 (eval dataset + harness) done — a 100-record persona with 75 gold questions, plus an isolation-only second tenant, seeded through the API and scored by a harness that runs on every PR. It reports zero cross-tenant leaks and correct supersede handling on all 20 preference-evolution questions; Recall/MRR read 0.00 until search lands in milestone 4. See the [Roadmap](#roadmap).

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

Eval (with the API running): `docker compose run --rm api python -m eval.harness --base-url http://api:8000` — seeds both personas as fresh tenants and prints the metrics table. Add `--require-retrieval` to also fail on the Recall/MRR bars. The dataset lives in `eval/data/`, its design in [`eval/personas.md`](eval/personas.md).

## Memory types

- **Facts** — durable assertions ("lives in London"). Point lookup + embedding search on one current value.
- **Preferences** — versioned opinions ("prefers tea to coffee"). Latest-valid-wins: a query sees the current value unless it explicitly asks historically.
- **Episodes** — timestamped events ("interviewed at X, 2026-03-04"). Many can coexist for the same topic; retrieval is recency/range-weighted, not latest-wins.

No Documents type — long-form text needs chunking, a different retrieval problem. No Policies type — behavior rules are an agent concern, not something retrieved to answer a question; representable as a Preference if ever needed.

## Architecture

**Multi-tenant from the schema up.** Every table carries `tenant_id`, enforced by Postgres Row-Level Security — not an app-level `WHERE` clause. RLS makes isolation a database-enforced invariant instead of a discipline every query has to remember; one missed filter in application code is a silent data leak.

**Three typed tables**, not one polymorphic table with a JSONB payload. `memory_facts`, `memory_preferences`, `memory_episodes` share a common shape (`id`, `tenant_id`, `content`, `confidence`, `valid_from`, `valid_to`, `created_at`, `source`, plus `embedding` from milestone 4) and add type-specific columns. Typed tables keep constraints and indexes real; JSONB would hide the structure that makes the types meaningfully different.

**Temporal validity, not overwrite.** `valid_from`/`valid_to` versions every row; a superseded preference points `superseded_by` at its replacement. A memory system that overwrites in place can't answer "what did I used to believe."

**Retrieval routes before it searches.** A rule-based classifier reads the question (date expressions → episodes, "prefer/like/hate" → preferences, else facts) and produces type + time hints. Search then runs hybrid (pgvector + full-text) per hinted table, always inside the tenant's RLS boundary, and results merge by similarity + recency + confidence. An LLM-based router is a natural v2 — deferred because it adds latency, cost, and non-determinism to every query; the eval harness can A/B it against this baseline later.

**Confidence is caller-supplied**, not inferred — there's one source per fact until an extraction pipeline exists. Ingestion is structured JSON only, no free-text extraction, so writes stay deterministic and auditable.

## Eval contract

Two synthetic tenants, no real user data in the repo. Tenant A carries the full seed set (100 records, 75 labeled questions) for retrieval quality. Tenant B is a minimal second tenant that exists only to probe isolation.

| Metric | Bar |
|---|---|
| Recall@5 / MRR | ≥ 0.9 / ≥ 0.8 on Tenant A |
| Cross-tenant leaks | 0, always — pass/fail, not a threshold |
| Routing accuracy | scored independently of retrieval quality |
| p95 latency | tracked from the caching milestone on |

The harness runs both suites against a live API and prints a metrics table with per-question failure diffs. It runs on every PR and fails it on any leak or supersede error — not an afterthought. Recall/MRR join the gate once search exists (milestone 4).

## How it all fits together (milestones 1–3)

A guided tour of what exists today — the tools, the classes, and the reasoning behind each choice. Everything here is built and tested; anything planned is marked with its milestone.

**In one paragraph:** Mutable is a FastAPI service in front of Postgres. Callers send JSON over HTTP with an `X-Tenant-Id` header; Pydantic validates it; SQLAlchemy turns it into rows in one of three typed tables. Postgres itself — not the Python code — guarantees one tenant can never see another's rows, using Row-Level Security. Preferences are never overwritten: a change closes the old row and links it to the new one, so history stays queryable. An eval harness seeds a fictional user through the API and checks all of this on every pull request.

### The big picture

```mermaid
flowchart LR
    subgraph callers["Callers"]
        curl["curl / any HTTP client"]
        harness["Eval harness<br/>eval/seed.py · eval/harness.py"]
        tests["pytest<br/>TestClient, in-process"]
    end

    subgraph compose["Docker Compose"]
        subgraph apibox["api container"]
            uvicorn["uvicorn<br/>ASGI server"] --> fastapi["FastAPI app<br/>app/main.py"]
            fastapi --> routers["Routers<br/>facts · preferences · episodes"]
            routers --> dep["get_tenant_db<br/>sets app.tenant_id"]
            dep --> orm["SQLAlchemy Session"]
        end
        subgraph dbbox["db container: Postgres 16 + pgvector"]
            rls{{"Row-Level Security<br/>one policy per table"}}
            tables[("tenants<br/>memory_facts<br/>memory_preferences<br/>memory_episodes")]
        end
    end

    alembic["Alembic<br/>migrations"]

    curl -- "HTTP + X-Tenant-Id" --> uvicorn
    harness -- "HTTP + X-Tenant-Id" --> uvicorn
    tests -- "direct ASGI call" --> fastapi
    orm -- "role memory_engine_app" --> rls
    rls --> tables
    alembic -- "role memory_engine (superuser)" --> tables
```

Two paths reach the database, deliberately with different rights: **the API** connects as a restricted role that RLS always applies to; **Alembic** connects as the owner/superuser because it needs to create tables, roles, and policies — and never serves a request.

### The toolbox: what each piece does here, and why

| Tool | Its job in this repo | Why this one | Alternatives, and why not (yet) |
|---|---|---|---|
| **Python 3.12** | Everything | Mature typing (`X \| None`, `Self`), the ecosystem for AI work later | — |
| **FastAPI** | HTTP layer: routing, request parsing, dependency injection (`Depends`), auto-generated docs at `/docs` | Validation comes free from type hints via Pydantic; `Depends` is how tenant scoping is attached to every request | **Flask**: no built-in validation or DI. **Django**: its ORM and admin are heavier than an API-only service needs |
| **uvicorn** | The server process that runs the FastAPI app | Standard ASGI server for FastAPI; `--reload` for dev | Gunicorn with uvicorn workers — a deploy-time concern (milestone 6) |
| **Pydantic** | Three jobs: API request/response shapes (`app/schemas.py`), config from env vars (`pydantic-settings`), validating hand-written eval YAML (`eval/dataset.py`) | One way to say "this data must look like this" everywhere, with clear errors | marshmallow; hand-rolled checks. **SQLModel** would merge Pydantic and SQLAlchemy classes — kept separate so the API contract and the table layout can differ (e.g. `supersedes` is input-only) |
| **SQLAlchemy 2.0** | ORM: Python classes ↔ tables (`app/models.py`), sessions, transactions | Typed `Mapped[...]` models; Alembic reads them to generate migrations | Raw SQL via psycopg: more control, but every query hand-written and no autogenerate |
| **psycopg 3** | The Postgres driver SQLAlchemy talks through | Current-generation driver | psycopg2 (older), asyncpg (async-only) |
| **PostgreSQL 16** | Storage, constraints, **Row-Level Security** | RLS makes isolation a database guarantee; CHECK constraints guard value ranges | A separate vector DB (Pinecone, Qdrant) would need its own, second isolation mechanism |
| **pgvector** | Extension enabled since migration `0001`; no vector column yet | Embeddings (milestone 4) live in the same rows, under the same RLS | See above |
| **Alembic** | Versioned schema migrations (`migrations/versions/`) | Creates tables *and* things an ORM can't express: roles, grants, RLS policies | `Base.metadata.create_all()`: no history, no upgrades, no roles/policies |
| **Docker + Compose** | `db` (pgvector image, healthcheck, persistent volume) and `api` (built from `Dockerfile`, code mounted for live reload) | Same Postgres + pgvector for everyone, one command to start; milestone 6 deploys this same file | Local installs — "works on my machine" drift |
| **pytest + TestClient** | 64 tests calling the app in-process against the **real** Postgres | Tests exercise the real RLS and constraints | SQLite or mocks would be faster but have no RLS or pgvector — they'd test a different system |
| **httpx** | HTTP client for the eval seed loader and harness | Same client type as `TestClient`, so one function works for tests *and* the live API | requests (no shared interface with TestClient) |
| **PyYAML** | Reads the eval dataset files | Hand-authored data needs comments and little punctuation | JSON (no comments); Python literals (data buried in code) |
| **Ruff** | Lint + formatting | One fast tool replacing flake8/isort/black | Those three separately |
| **GitHub Actions** | CI on every PR and push to `main` | Lives next to the code; free for this scale | Any CI would do |

### What happens during one request

Following `POST /preferences` that replaces an older preference — the most involved write in the system:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as FastAPI
    participant D as get_tenant_db
    participant R as create_preference
    participant PG as Postgres

    C->>F: POST /preferences, X-Tenant-Id header, JSON body
    F->>F: Pydantic validates body as MemoryPreferenceCreate (bad input stops here with 422)
    F->>D: resolve dependencies (header to UUID, open a session)
    D->>PG: set_config('app.tenant_id', tenant, is_local = true)
    D->>PG: INSERT INTO tenants ... ON CONFLICT DO NOTHING
    F->>R: call the endpoint with the payload and the session
    R->>PG: INSERT new row (RLS WITH CHECK: tenant_id must match)
    opt payload.supersedes is set
        R->>PG: load the old row (another tenant's row is invisible, so 404)
        R->>PG: old.valid_to = new.valid_from, old.superseded_by = new.id
    end
    R-->>F: ORM object
    F-->>C: 201 Created, serialized via MemoryPreferenceRead
    D->>PG: COMMIT in the dependency's cleanup, or ROLLBACK on error
```

Three details make tenant scoping hold:

- **`set_config(..., is_local = true)`** scopes the tenant to *this transaction only*. Pooled connections get reused across requests; a session-wide setting would leak one request's tenant into the next.
- **The tenant row is inserted implicitly** on first use — no signup. Safe because `tenants` has an RLS policy too: a caller can only ever insert *their own* id.
- **One transaction per request**, committed at the very end. Committing earlier would end the transaction and with it the tenant setting, before the endpoint's own queries ran.

### Isolation: two roles and one policy

```mermaid
flowchart TB
    admin["memory_engine<br/>superuser, owns the tables<br/>used by Alembic only"]
    app["memory_engine_app<br/>not an owner, not a superuser<br/>used by the running API"]
    policy{{"policy tenant_isolation, on every table<br/>USING and WITH CHECK:<br/>tenant_id = current_setting('app.tenant_id')"}}
    tables[("tenants · memory_facts<br/>memory_preferences · memory_episodes")]

    admin -- "DDL: tables, roles, policies<br/>RLS never applies to it" --> tables
    app -- "SELECT / INSERT / UPDATE / DELETE only" --> policy
    policy -- "rows of the current tenant only" --> tables
```

`USING` filters what a query can *see*; `WITH CHECK` blocks *writing* a row for another tenant. If `app.tenant_id` was never set, the policy raises an error instead of quietly matching nothing.

| Isolation approach | How it works | Why not chosen |
|---|---|---|
| **Postgres RLS** ✅ | The database filters every row by the transaction's tenant | — (cost: every connection must set the tenant, which `get_tenant_db` does) |
| `WHERE tenant_id = ...` in Python | Every query remembers to filter | One forgotten filter is a silent data leak |
| Schema per tenant | Each tenant gets its own copy of the tables | Migrations multiply by tenant count; cross-tenant ops get awkward |
| Database per tenant | Strongest separation | Heavy to operate for many small tenants |

It's proven twice: `tests/test_isolation.py` connects to Postgres *directly* as the API's role and shows each tenant sees only its own rows; the eval harness probes all 128 seeded records as the wrong tenant on every PR.

### The data model

```mermaid
erDiagram
    tenants ||--o{ memory_facts : owns
    tenants ||--o{ memory_preferences : owns
    tenants ||--o{ memory_episodes : owns
    memory_preferences |o--o| memory_preferences : "superseded_by"

    tenants {
        uuid id PK
        timestamptz created_at
    }
    memory_facts {
        uuid id PK
        uuid tenant_id FK
        text content
        float confidence "0 to 1"
        text source
        timestamptz valid_from
        timestamptz valid_to "null means current"
        timestamptz created_at
    }
    memory_preferences {
        uuid id PK
        uuid tenant_id FK
        text content
        float confidence "0 to 1"
        float strength "-1 to 1, negative means dislike"
        uuid superseded_by FK "the replacement"
        text source
        timestamptz valid_from
        timestamptz valid_to "null means current"
        timestamptz created_at
    }
    memory_episodes {
        uuid id PK
        uuid tenant_id FK
        text content
        float confidence "0 to 1"
        timestamptz event_time
        timestamptz event_time_end "multi-day events"
        text source
        timestamptz valid_from
        timestamptz valid_to
        timestamptz created_at
    }
```

**How a preference changes.** Nothing is overwritten. The old row is closed exactly where the new one starts, so at any moment exactly one version is valid. Here is Maya's caffeine preference as stored in the eval dataset:

```mermaid
gantt
    title maya.pref.caffeine, three versions
    dateFormat YYYY-MM-DD
    axisFormat %Y
    todayMarker off
    section Versions
    v1 strong black coffee          :done, c1, 2013-09-01, 2021-01-15
    v2 one flat white a day         :done, c2, 2021-01-15, 2024-11-01
    v3 tea over coffee (current)    :active, c3, 2024-11-01, 2026-09-27
```

"What does she drink now?" → the row with `valid_to = null`. "What did she drink in 2022?" → the row whose window contains 2022. Callers may backdate `valid_from` so real history can be recorded; a replacement dated before the row it replaces is rejected.

| Data-model decision | Chosen | Alternative | Trade-off accepted |
|---|---|---|---|
| Table layout | Three typed tables | One table with a JSONB payload | A little repetition across tables, in exchange for real constraints and columns per type |
| Change history | `valid_from`/`valid_to` + `superseded_by` | Overwrite in place; separate audit-log table | Queries must filter `valid_to IS NULL` for "current" |
| Which types version | Preferences only | Versioning for facts too | A changed fact is written in the past tense ("worked at Studio Loop 2019–2024") until facts get supersede |
| Confidence | Supplied by the caller | Inferred by the system | Nothing to infer from until free-text extraction (milestone 8) |

### How the Python classes work together

**The API (`app/`).** Every memory type has the same four-part shape; preferences are shown, facts and episodes mirror it:

```mermaid
classDiagram
    direction LR

    class Settings {
        <<pydantic-settings>>
        database_url
        admin_database_url
    }
    class Base {
        <<SQLAlchemy DeclarativeBase>>
    }
    class MemoryPreference {
        <<table row>>
        id, tenant_id, content
        confidence, strength
        superseded_by
        valid_from, valid_to
    }
    class MemoryPreferenceCreate {
        <<Pydantic: request body>>
        content, confidence, strength
        valid_from optional
        supersedes optional
    }
    class MemoryPreferenceRead {
        <<Pydantic: response body>>
        every stored column
    }
    class PreferencesRouter {
        <<APIRouter /preferences>>
        create_preference()
        list_preferences()
        get_preference()
        delete_preference()
    }
    class get_tenant_db {
        <<FastAPI dependency>>
        sets app.tenant_id
        owns the transaction
    }

    Base <|-- MemoryPreference
    Base <|-- Tenant
    Base <|-- MemoryFact
    Base <|-- MemoryEpisode
    PreferencesRouter ..> MemoryPreferenceCreate : validates input
    PreferencesRouter ..> MemoryPreference : reads and writes
    PreferencesRouter ..> MemoryPreferenceRead : shapes output
    PreferencesRouter ..> get_tenant_db : Depends
    get_tenant_db ..> Settings : engine from database_url
```

Why two kinds of class per type: the **SQLAlchemy model** is what a row *is*; the **Pydantic schemas** are what callers may *send* and will *get back*. They differ on purpose — a caller can't send an `id` or `tenant_id`, and `supersedes` is an instruction, not a column. `MemoryPreferenceRead` builds itself straight from the ORM object (`from_attributes`).

**The eval (`eval/`), part 1 — what the YAML becomes** (`dataset.py`). Every class here inherits from a small `_Strict` base that makes Pydantic reject unknown fields, so a typo in the YAML fails loudly instead of being silently dropped:

```mermaid
classDiagram
    direction LR

    class Persona {
        records
        questions
        expected_route()
        check_questions()
    }
    class PersonaRecords {
        persona name
        check_records()
    }
    class GoldQuestion {
        id, question, category
        gold, must_exclude, as_of
    }
    class _Record {
        <<shared fields>>
        key, content, confidence
        source, valid_from
    }
    class SeedFact
    class SeedPreference {
        strength
        supersedes
    }
    class SeedEpisode {
        event_time
        event_time_end
    }

    Persona *-- PersonaRecords
    Persona o-- GoldQuestion
    PersonaRecords o-- SeedFact : facts
    PersonaRecords o-- SeedPreference : preferences
    PersonaRecords o-- SeedEpisode : episodes
    _Record <|-- SeedFact
    _Record <|-- SeedPreference
    _Record <|-- SeedEpisode
```

**Part 2 — what a run produces** (`seed.py`, `harness.py`):

```mermaid
classDiagram
    direction LR

    class SeededPersona {
        <<dataclass>>
        tenant_id
        ids: key to UUID
    }
    class SeededTenant {
        <<dataclass>>
        name, persona, seeded
    }
    class Retrieved {
        <<dataclass>>
        ids, ranked
        route
    }
    class QuestionResult {
        <<dataclass>>
        missing, excluded_hits, leaked
        recall, reciprocal_rank
    }
    class Report {
        <<dataclass>>
        isolation_leaks
        supersede_failures
        recall, mrr
        passed()
    }

    SeededTenant --> Persona : the dataset
    SeededTenant --> SeededPersona : what seeding returned
    Report o-- SeededTenant
    Report o-- QuestionResult : one per question
    QuestionResult --> GoldQuestion : scored against
    QuestionResult ..> Retrieved : scored from
```

The dividing line: **Pydantic** classes guard data coming *in* from hand-written YAML (typos and bad labels fail loudly); **dataclasses** carry data the code itself produced (seeding results, scores), which needs no validation.

### The eval pipeline

```mermaid
flowchart LR
    yaml["eval/data/maya, eval/data/jonas<br/>records.yaml · questions.yaml"] --> ds["dataset.py<br/>load_persona()<br/>validate every rule"]
    ds --> seed["seed.py<br/>seed_persona()<br/>POST each record,<br/>fresh tenant per run"]
    seed --> ids["key to UUID map"]
    ids --> iso["check_isolation<br/>128 records + 6 lists,<br/>as the wrong tenant"]
    ids --> sup["check_supersede<br/>10 links + 20 evolution<br/>questions vs API state"]
    ids --> ret["score_question x 75<br/>Recall@5 · MRR ·<br/>excluded hits · leaks"]
    iso & sup & ret --> rep["Report<br/>metrics table + diffs<br/>exit 0 or 1"]
```

| Eval decision | Chosen | Alternative | Why |
|---|---|---|---|
| Data source | Two fictional personas, hand-written | Real data; LLM-generated data | No real personal data in the repo; hand-written gold labels are trustworthy |
| How records get in | Through the public API | Direct SQL inserts | Exercises the same validation, supersede logic, and RLS a real caller hits |
| Record identity | Stable keys (`maya.pref.diet.v2`) | UUIDs in the files | UUIDs are assigned by the server; keys are readable and stable |
| Re-runs | A new tenant every run | Wiping the database | Nothing to clean up; runs can't interfere with each other |
| What retrieval sees | Only the question text | The gold labels | A search that could peek at the answers would score meaninglessly |
| The second persona | Different content, **same topics** as Maya's questions | Unrelated topics | A leaked record can only show up in results if it would actually rank |

### CI: what runs on every pull request

```mermaid
flowchart LR
    trig["PR opened or updated,<br/>or push to main"] --> setup["Postgres service container<br/>+ Python 3.12 + deps"]
    setup --> lint["ruff check"]
    lint --> mig["alembic upgrade head"]
    mig --> test["pytest<br/>64 tests"]
    test --> up["start uvicorn"]
    up --> ev["python -m eval.harness"]
    ev --> gate{"0 leaks and<br/>0 supersede failures?"}
    gate -- yes --> ok["check passes"]
    gate -- no --> bad["check fails"]
```

The harness report is also written to the run's summary page, readable from the PR's Checks tab. Recall/MRR are printed but don't fail the check until search exists (milestone 4 turns on `--require-retrieval`).

### Where things live

| Path | What's in it |
|---|---|
| `app/main.py` | Creates the FastAPI app, mounts the routers, `/health`, `/health/db`, `/whoami` |
| `app/config.py` | `Settings`: the two database URLs, read from env vars or `.env` |
| `app/db.py` | Engine, session factory, and the `get_tenant_id` / `get_tenant_db` dependencies |
| `app/models.py` | SQLAlchemy models — the tables |
| `app/schemas.py` | Pydantic models — the API's request and response shapes |
| `app/routers/` | One file per memory type: create, list current, get by id, delete |
| `migrations/versions/` | Seven migrations, in order: pgvector → tenants → facts → preferences → episodes → app role → RLS |
| `tests/` | API tests per type, the direct-Postgres isolation test, dataset/seed/harness tests |
| `eval/personas.md` | Design doc for the two fictional users |
| `eval/data/` | The dataset: records and gold questions per persona |
| `eval/dataset.py` · `seed.py` · `harness.py` | Validate → seed → score |
| `Dockerfile` · `docker-compose.yml` | The two containers |
| `.github/workflows/ci.yml` | The CI pipeline above |

### Known gaps (honest list)

- **No authentication yet.** The API trusts whatever `X-Tenant-Id` it's given, so anyone who knows or guesses a tenant id can act as that tenant. RLS guarantees tenants can't see *each other* — not that a caller is who they claim. Real auth is milestone 7.
- **Deletes are hard deletes,** which sits awkwardly with "never lose history" — and there's a bug: the commit runs in `get_tenant_db`'s cleanup, *after* the response is sent, so an error that only surfaces at commit time is reported to the caller as success. Example: deleting a preference that an older version still points to via `superseded_by` returns `204`, but the row is not deleted.
- **Facts can't be superseded** — only preferences version (see the data model table).
- **No search yet.** pgvector is installed but unused; embeddings, hybrid search, and the router are milestone 4.
- **Sync endpoints.** Routes are plain `def`, so FastAPI runs them in a thread pool. Simple and fine at this scale; async SQLAlchemy is an option if load ever demands it.

## Roadmap

Each milestone ships something runnable and checkable on its own — none depends on a later one to be demoable. **For the user** says what it means from the product side; **Ships** and **Done when** say what gets built and how it's checked.

### 1. Scaffold ✅
**For the user:** nothing visible yet — the foundation that makes every later change safe to ship.

**Ships:** Docker Compose running Postgres with pgvector enabled, a migration tool wired up, CI running lint and tests on every push.

**Done when:** `docker compose up` gives a working local Postgres+pgvector; an empty migration and empty test suite both go green in CI.

### 2. Schema + tenant-scoped ingestion ✅
**For the user:** their memories are stored in a structured, versioned way, and no other user can ever see them — guaranteed by the database, not by careful code.

**Ships:** the three typed tables (`memory_facts`, `memory_preferences`, `memory_episodes`) with `tenant_id` and RLS policies from the first migration, plus a CRUD API per type with versioning on write.

**Done when:** two tenants are seeded through the API, and a direct Postgres session for one tenant provably cannot read the other's rows.

### 3. Eval dataset & harness v1 ✅
**For the user:** before building search, pin down what "remembering correctly" means — above all, that a changed preference is recalled as it is *now*, not as it used to be — and measure it on every change.

**Ships:** a fictional user, Maya (100 records, 75 hand-labeled questions), and an isolation-only second user, Jonas (28 records), seeded through the API; a harness that checks isolation, supersede handling, and retrieval, printing a metrics table with per-question failure diffs. A fifth of the questions target preference evolution: a "current" question must exclude the superseded record, a historical one must still find it.

**Done when:** the harness runs end-to-end and reports zero cross-tenant leaks and correct supersede handling on every preference-evolution question, with Recall/MRR near zero until milestone 4 adds search.

### 4. Search + routing
**For the user:** the assistant can *recall*. Before it answers or acts ("book me dinner on Friday"), it asks its memory a plain-language question ("what should I know about Maya's food?") and gets back the right records — pescatarian, shellfish allergy, dislikes cilantro — and never the outdated "vegetarian".

**Ships:**
- `/search`: a question in, ranked records out. Records, not prose — turning them into an answer is milestone 9.
- Embeddings computed on write, and hybrid search per type: vectors for meaning, full-text for exact words, merged by rank.
- A rule-based router that picks the record types *and the time scope*: current by default, as of a date ("back in 2023"), or full history ("used to"). Out-of-date versions are filtered out by time, not just ranked lower.
- The harness calls `/search` instead of its stub, and CI starts failing PRs on the Recall/MRR bars.

**Done when:** Recall@5 ≥ 0.9 / MRR ≥ 0.8 on Maya — including a held-out set of questions never used for tuning — with zero leaks and no superseded version returned when a question asks about now.

### 5. Caching
**For the user:** recall feels instant, so looking something up never slows a conversation down.

**Ships:** a Redis-backed embedding cache and hot-query cache, keyed per tenant.

**Done when:** the eval harness shows a measured p95 latency drop with identical Recall/MRR/isolation results — proof the cache is invisible to correctness.

### 6. Deploy + CI/CD
**For the user:** Mutable is reachable on the internet, and a change that could leak one user's memories to another cannot ship.

**Ships:** the same `docker-compose.yml` from milestone 1, deployed to a single AWS EC2 instance (not ECS/RDS — cheapest option, and the closest match to local dev, at the cost of self-managed Postgres backups instead of RDS's); CI/CD running the full eval harness (isolation gate included) as a required check before deploy.

**Done when:** there's a live endpoint on a public IP/DNS name, and a PR that breaks tenant scoping gets blocked by a red eval run before it can merge.

### 7. Accounts & billing
**For the user:** they sign up and get their own key, and nobody can pose as them — today the API simply trusts whatever tenant id it's given.

**Ships:** real signup/login replacing the caller-supplied opaque tenant ID, API-key issuance, basic plan gating.

**Done when:** a new tenant signs up through a real auth flow and gets a scoped key that RLS enforces exactly as it does today.

### 8. Free-text ingestion
**For the user:** they (or their assistant) just say things naturally — "I've gone pescatarian" — and Mutable turns it into the right record, recognizing when it updates something it already knew.

**Ships:** an endpoint that accepts raw text and calls an LLM to extract structured facts/preferences/episodes into the existing schema.

**Done when:** pasting an unstructured paragraph produces the same typed, versioned rows a structured POST would, with extraction confidence populated and reviewable before commit.

### 9. Answer synthesis (RAG)
**For the user:** a direct answer instead of a list of records — with the memories it came from shown, so they can trust it or correct it.

**Ships:** an optional endpoint that takes retrieved records and generates a prose answer via an LLM, on top of (not instead of) the existing retrieval endpoint.

**Done when:** a question returns a synthesized answer that cites the specific record IDs it drew from.

### 10. Client layer
**For the user:** the first thing a non-developer can use — tell it things, ask it things, see what it remembers, and fix what's wrong.

**Ships:** a thin UI or chat interface consuming the existing API — the first real product surface on top of the engine.

**Done when:** someone who isn't you can add and query memories without touching curl or Postman.

### 11. Document/vault ingestion
**For the user:** hand over whole documents — notes, a CV, a journal — and ask about them, not just short statements.

**Ships:** chunked ingestion for long-form text, likely a new memory type with its own retrieval strategy.

**Done when:** a full document can be ingested and a question against it returns the right chunk, evaluated against its own gold set.

### 12. Autonomous agent behavior
**For the user:** the assistant acts on what it knows — schedules, reminders, decisions — and can always show which memory led to which action.

**Ships:** a policy layer letting an agent act on stored memory (schedule, notify, decide), not just retrieve it.

**Done when:** an agent takes a real action informed by a memory lookup, with an audit trail of which memory drove which action.
