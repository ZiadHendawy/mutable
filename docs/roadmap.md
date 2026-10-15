# Roadmap

Each milestone ships something that runs and can be checked on its own; none depends on a later one to be demonstrated. For each milestone:

- **For the user:** what it means from the product side
- **Ships:** what gets built
- **Done when:** how it's checked

| # | Milestone | |
|---|---|---|
| 1 | [Scaffold](#1-scaffold) | ✅ |
| 2 | [Storage](#2-storage) | ✅ |
| 3 | [Eval](#3-eval) | ✅ |
| 4 | [Search](#4-search) | 🚧 in progress |
| 5 | [Caching](#5-caching) | |
| 6 | [Deploy](#6-deploy) | |
| 7 | [Accounts](#7-accounts) | |
| 8 | [Free-text input](#8-free-text-input) | |
| 9 | [Answers](#9-answers) | |
| 10 | [Client app](#10-client-app) | |
| 11 | [Documents](#11-documents) | |
| 12 | [Agent actions](#12-agent-actions) | |

## 1. Scaffold

✅ Done.

**For the user:** nothing visible yet. This is the foundation that makes every later change safe to ship.

**Ships:** Docker Compose running Postgres with pgvector, migrations wired up, and CI running lint and tests on every push.

**Done when:** `docker compose up` gives a working local Postgres with pgvector, and an empty migration and an empty test suite both pass in CI.

## 2. Storage

✅ Done.

**For the user:** their memories are stored in a structured, versioned way, and no other user can ever see them. The database guarantees this, not careful code.

**Ships:** the three tables (`memory_facts`, `memory_preferences`, `memory_episodes`), each with a `tenant_id` and a Row-Level Security rule, plus an API per type to create, list, get and delete. Preferences keep their versions when they change.

**Done when:** two tenants' records are written through the API, and a direct Postgres session for one tenant provably can't read the other's rows.

## 3. Eval

✅ Done.

**For the user:** before building search, pin down what "remembering correctly" means, and check it on every change. Above all, a changed preference must be recalled as it is *now*, not as it used to be.

**Ships:**
- A fictional user, Maya: 100 records and 75 hand-labeled questions.
- An isolation-only second user, Jonas: 28 records.
- Both are written through the API.
- An eval that checks isolation, preference history and search, and prints a table of scores with the details of every failed question.

A quarter of the questions are about preferences that changed. A "current" question must exclude the outdated version, and a historical one must still find it. See [eval.md](eval.md).

**Done when:** the eval runs end to end and reports zero leaks between users and correct history on every changed-preference question. Recall and MRR stay near zero until milestone 4 adds search.

## 4. Search

🚧 In progress.

**For the user:** the assistant can *recall*. Before it answers or acts ("book me dinner on Friday"), it asks its memory a plain-language question ("what should I know about Maya's food?"). It gets back the right records (pescatarian, shellfish allergy, dislikes cilantro) and never the outdated "vegetarian".

**Ships:**
- `/search`: a question in, ranked records out. Records, not prose; turning them into an answer is milestone 9.
- Embeddings computed when a record is written, and hybrid search per type: vectors for meaning, full-text for exact words, merged by rank.
- A rule-based router that picks the record types *and the time scope*:
  - current, the default
  - as of a date: "back in 2023"
  - full history: "used to"

  Out-of-date versions are filtered out by date, not just ranked lower.
- The eval calls `/search` instead of its placeholder, and CI starts failing pull requests that miss the Recall and MRR bars.

**Done when:**
- Recall@5 ≥ 0.9 and MRR ≥ 0.8 on Maya's questions, including the held-out questions never used for tuning.
- Zero leaks.
- No outdated version is returned when a question asks about now.

**Steps.** One pull request each, small enough to review on its own:

| # | Step | |
|---|---|---|
| 1 | Held-out questions: 20 more, never used for tuning, reported only as a total | ✅ |
| 2 | Embedding model: one interface, the real model, and a predictable fake for tests | |
| 3 | Store embeddings and a full-text index on every record, computed on write | |
| 4 | `/search` v1: vector search over current records; the eval calls it, giving the first real scores | |
| 5 | Hybrid search: add full-text, merge both rankings | |
| 6 | Router, time scope: current, as of a date, or full history | |
| 7 | Router, record types: which tables to search, reported so the eval can score it | |
| 8 | Episode dates: "in October 2025" filters by date; "last" sorts newest first | |
| 9 | Reach the bars on the main questions; check the held-out score once, at the end | |
| 10 | Turn on the CI gate for Recall and MRR, and for "no outdated version for 'now' questions" | |

## 5. Caching

**For the user:** recall feels instant, so looking something up never slows a conversation down.

**Ships:** a Redis cache for embeddings and frequent queries, kept separate per tenant.

**Done when:** the eval shows a measured drop in p95 latency, with identical Recall, MRR and isolation results. That's the proof the cache never changes an answer.

## 6. Deploy

**For the user:** Mutable is reachable on the internet, and a change that could leak one user's memories to another can't ship.

**Ships:**
- The same `docker-compose.yml` from milestone 1, deployed to a single AWS EC2 server.
  - Why not ECS or RDS: EC2 is the cheapest option and the closest match to local development.
  - The cost: managing Postgres backups ourselves instead of RDS doing it.
- The full eval, including the isolation gate, as a required check before every deploy.

**Done when:** there's a live endpoint on a public address, and a pull request that breaks tenant isolation is blocked by a failing eval before it can merge.

## 7. Accounts

**For the user:** they sign up and get their own key, and nobody can pose as them. Today the API simply trusts whatever tenant id it's given.

**Ships:** real sign-up and login in place of the caller-supplied tenant id, API keys, and basic plan limits.

**Done when:** a new user signs up through a real login flow and gets a key that Row-Level Security enforces exactly as it does today.

## 8. Free-text input

**For the user:** they, or their assistant, just say things naturally ("I've gone pescatarian"), and Mutable turns that into the right record. It also recognizes when the new statement updates something it already knew.

**Ships:** an endpoint that accepts plain text and uses an LLM to turn it into facts, preferences and episodes in the existing tables.

**Done when:** pasting a paragraph of plain text produces the same typed, versioned records a structured request would, with a confidence score on each, and the records can be reviewed before they're saved.

## 9. Answers

**For the user:** a direct answer instead of a list of records, with the memories it came from shown, so they can trust it or correct it.

**Ships:** an optional endpoint that takes the records search found and writes a prose answer with an LLM. It sits on top of search and doesn't replace it.

**Done when:** a question returns a written answer that cites the ids of the records it drew from.

## 10. Client app

**For the user:** the first thing a non-developer can use. They can tell it things, ask it things, see what it remembers, and fix what's wrong.

**Ships:** a simple web or chat interface on top of the existing API; the first real product surface.

**Done when:** someone other than the developer can add and look up memories without curl or Postman.

## 11. Documents

**For the user:** they can hand over whole documents (notes, a CV, a journal) and ask about them, not just short statements.

**Ships:** a way to store long text by splitting it into chunks, probably as a new memory type with its own search strategy.

**Done when:** a whole document can be stored, and a question about it returns the right chunk, checked against its own set of questions and expected answers.

## 12. Agent actions

**For the user:** the assistant acts on what it knows (schedules, reminders, decisions) and can always show which memory led to which action.

**Ships:** a layer that lets an agent act on stored memories (schedule, notify, decide), not just look them up.

**Done when:** an agent takes a real action based on a memory lookup, with an audit trail of which memory led to which action.
