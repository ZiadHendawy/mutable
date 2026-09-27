"""Eval harness: seed every persona, then score isolation, supersede handling, and retrieval.

    python -m eval.harness [--base-url http://localhost:8000] [--require-retrieval]

Exits non-zero when a gate fails: any cross-tenant leak, or any supersede check. Retrieval
metrics are reported against the README's bars but only gate the run with
--require-retrieval, since there is no search endpoint until milestone 4.
"""

import argparse
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from eval.dataset import GoldQuestion, Persona, RecordType, load_persona
from eval.seed import SeededPersona, seed_persona

PERSONAS = ["maya", "jonas"]
PATHS: dict[RecordType, str] = {
    "fact": "/facts",
    "preference": "/preferences",
    "episode": "/episodes",
}
RECALL_BAR = 0.9
MRR_BAR = 0.8


@dataclass
class Retrieved:
    ids: list[uuid.UUID]  # ranked, best first
    route: set[RecordType] | None = None  # types the router chose, if it reports them


# (client, tenant id, question text) -> ranked results. Gets only what a real caller has --
# the question text -- never the gold labels.
Retriever = Callable[[httpx.Client, uuid.UUID, str], Retrieved]


def no_search(client: httpx.Client, tenant_id: uuid.UUID, question: str) -> Retrieved:
    """Placeholder until milestone 4 adds search: finds nothing."""
    return Retrieved(ids=[])


@dataclass
class SeededTenant:
    name: str
    persona: Persona
    seeded: SeededPersona

    @property
    def key_of(self) -> dict[uuid.UUID, str]:
        return {id_: key for key, id_ in self.seeded.ids.items()}

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Tenant-Id": str(self.seeded.tenant_id)}


def seed_all(client: httpx.Client, names: list[str] = PERSONAS) -> list[SeededTenant]:
    # Load (and so validate) everything before writing anything.
    personas = {name: load_persona(name) for name in names}
    return [
        SeededTenant(name, persona, seed_persona(client, persona.records))
        for name, persona in personas.items()
    ]


# --- Isolation --------------------------------------------------------------------------


def check_isolation(client: httpx.Client, tenants: list[SeededTenant]) -> tuple[list[str], int]:
    """Every record, fetched by id and via every list endpoint, as every *other* tenant.

    Returns (leaks, number of probes made).
    """
    leaks: list[str] = []
    probes = 0
    for owner in tenants:
        owned = owner.key_of
        for other in tenants:
            if other is owner:
                continue
            for key, id_ in owner.seeded.ids.items():
                path = PATHS[owner.persona.records.record_type(key)]
                status = client.get(f"{path}/{id_}", headers=other.headers).status_code
                probes += 1
                if status != 404:
                    leaks.append(f"{other.name} got {status} for {owner.name}'s {key}")
            for path in PATHS.values():
                listed = client.get(path, headers=other.headers).json()
                probes += 1
                for row in listed:
                    id_ = uuid.UUID(row["id"])
                    if id_ in owned:
                        leaks.append(f"{other.name} sees {owned[id_]} in GET {path}")
    return leaks, probes


# --- Supersede handling -----------------------------------------------------------------


def check_supersede(client: httpx.Client, tenant: SeededTenant) -> list[str]:
    """Checks the API's actual state, not the dataset: every chain is linked and tiles in
    time, and every preference-evolution question's gold/must_exclude agrees with it."""
    records = tenant.persona.records
    ids = tenant.seeded.ids
    rows = {
        p.key: client.get(f"/preferences/{ids[p.key]}", headers=tenant.headers).json()
        for p in records.preferences
    }
    current = {
        uuid.UUID(r["id"]) for r in client.get("/preferences", headers=tenant.headers).json()
    }
    successor = records.successor_of()
    failures: list[str] = []

    for key, row in rows.items():
        nxt = successor.get(key)
        if nxt is None:
            if row["valid_to"] is not None or row["superseded_by"] is not None:
                failures.append(f"{key} should be current but is closed")
            if ids[key] not in current:
                failures.append(f"{key} is missing from GET /preferences")
            continue
        if row["superseded_by"] != str(ids[nxt]):
            failures.append(f"{key} should be superseded_by {nxt}")
        if row["valid_to"] is None or _dt(row["valid_to"]) != _dt(rows[nxt]["valid_from"]):
            failures.append(f"{key} should close exactly when {nxt} starts")
        if ids[key] in current:
            failures.append(f"{key} is superseded but still listed as current")

    for q in _evolution_questions(tenant.persona):
        gold = [k for k in q.gold if k in rows]
        excluded = [k for k in q.must_exclude if k in rows]
        if q.category == "preference_current":
            failures += [f"{q.id}: gold {k} is not current" for k in gold if ids[k] not in current]
            failures += [
                f"{q.id}: excluded {k} is still current" for k in excluded if ids[k] in current
            ]
        if q.as_of is not None:
            when = q.as_of.date()
            failures += [
                f"{q.id}: gold {k} was not valid on {when}"
                for k in gold
                if not _valid_at(rows[k], q.as_of)
            ]
            failures += [
                f"{q.id}: excluded {k} was valid on {when}"
                for k in excluded
                if _valid_at(rows[k], q.as_of)
            ]
    return [f"{tenant.name}: {f}" for f in failures]


def _evolution_questions(persona: Persona) -> list[GoldQuestion]:
    return [
        q
        for q in persona.questions
        if q.category in ("preference_current", "preference_historical")
    ]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _valid_at(row: dict, when: datetime) -> bool:
    if _dt(row["valid_from"]) > when:
        return False
    return row["valid_to"] is None or when < _dt(row["valid_to"])


# --- Retrieval --------------------------------------------------------------------------


@dataclass
class QuestionResult:
    question: GoldQuestion
    missing: list[str]  # gold keys not in the top k
    excluded_hits: list[str]  # must_exclude keys that made the top k
    leaked: list[str]  # top-k results that belong to another tenant
    reciprocal_rank: float
    route_ok: bool | None  # None when the retriever doesn't report a route

    @property
    def recall(self) -> float:
        gold = self.question.gold
        return (len(gold) - len(self.missing)) / len(gold)

    @property
    def passed(self) -> bool:
        return not (self.missing or self.excluded_hits or self.leaked)


def score_question(
    question: GoldQuestion,
    retrieved: Retrieved,
    tenant: SeededTenant,
    others: list[SeededTenant],
    k: int,
) -> QuestionResult:
    own = tenant.key_of
    top = retrieved.ids[:k]
    top_keys = [own[id_] for id_ in top if id_ in own]

    leaked = []
    for id_ in top:
        if id_ in own:
            continue
        owner = next((o for o in others if id_ in o.key_of), None)
        leaked.append(owner.key_of[id_] if owner else f"id {id_} from another tenant")

    rank = next((i for i, key in enumerate(top_keys, 1) if key in question.gold), None)
    route_ok = None
    if retrieved.route is not None:
        route_ok = retrieved.route == tenant.persona.expected_route(question)
    return QuestionResult(
        question=question,
        missing=[key for key in question.gold if key not in top_keys],
        excluded_hits=[key for key in question.must_exclude if key in top_keys],
        leaked=leaked,
        reciprocal_rank=1 / rank if rank else 0.0,
        route_ok=route_ok,
    )


# --- Run & report -----------------------------------------------------------------------


@dataclass
class Report:
    tenants: list[SeededTenant]
    retriever: str
    k: int
    isolation_leaks: list[str]
    isolation_probes: int
    supersede_failures: list[str]
    results: list[QuestionResult]

    @property
    def retrieval_leaks(self) -> int:
        return sum(len(r.leaked) for r in self.results)

    @property
    def leaks(self) -> int:
        return len(self.isolation_leaks) + self.retrieval_leaks

    @property
    def recall(self) -> float:
        return _mean(r.recall for r in self.results)

    @property
    def mrr(self) -> float:
        return _mean(r.reciprocal_rank for r in self.results)

    def passed(self, require_retrieval: bool = False) -> bool:
        gates = self.leaks == 0 and not self.supersede_failures
        if require_retrieval:
            gates = gates and self.recall >= RECALL_BAR and self.mrr >= MRR_BAR
        return gates


def evaluate(
    client: httpx.Client,
    tenants: list[SeededTenant],
    retriever: Retriever = no_search,
    k: int = 5,
) -> Report:
    leaks, probes = check_isolation(client, tenants)
    supersede = [f for t in tenants for f in check_supersede(client, t)]
    results = []
    for tenant in tenants:
        others = [t for t in tenants if t is not tenant]
        for q in tenant.persona.questions:
            retrieved = retriever(client, tenant.seeded.tenant_id, q.question)
            results.append(score_question(q, retrieved, tenant, others, k))
    return Report(
        tenants=tenants,
        retriever=getattr(retriever, "__name__", type(retriever).__name__),
        k=k,
        isolation_leaks=leaks,
        isolation_probes=probes,
        supersede_failures=supersede,
        results=results,
    )


def format_report(report: Report, require_retrieval: bool = False) -> str:
    k = report.k
    seeded = ", ".join(f"{t.name}: {len(t.seeded.ids)} records" for t in report.tenants)
    links = sum(len(t.persona.records.successor_of()) for t in report.tenants)
    evolution = sum(len(_evolution_questions(t.persona)) for t in report.tenants)
    lines = [
        f"Mutable eval -- seeded {seeded}; retriever: {report.retriever}",
        "",
        "Gates",
        f"  Cross-tenant leaks   {report.leaks:>4}   {_mark(report.leaks == 0)}"
        f"   ({report.isolation_probes} isolation probes + retrieval results)",
        f"  Supersede failures   {len(report.supersede_failures):>4}"
        f"   {_mark(not report.supersede_failures)}"
        f"   ({links} supersede links, {evolution} preference-evolution questions)",
        "",
        f"Retrieval (k={k})              n   Recall@{k}     MRR   excluded hits",
    ]
    categories = sorted({r.question.category for r in report.results})
    for category in [*categories, "all"]:
        rows = [r for r in report.results if category in ("all", r.question.category)]
        lines.append(
            f"  {category:<24}{len(rows):>5}{_mean(r.recall for r in rows):>11.2f}"
            f"{_mean(r.reciprocal_rank for r in rows):>8.2f}"
            f"{sum(len(r.excluded_hits) for r in rows):>16}"
        )
    gating = "" if require_retrieval else "  (not gating; pass --require-retrieval)"
    lines.append(
        f"  Bars: Recall@{k} >= {RECALL_BAR} {_mark(report.recall >= RECALL_BAR)},"
        f" MRR >= {MRR_BAR} {_mark(report.mrr >= MRR_BAR)}{gating}"
    )
    routed = [r.route_ok for r in report.results if r.route_ok is not None]
    routing = f"{_mean(routed):.2f}" if routed else "n/a (retriever reports no route)"
    lines.append(f"  Routing accuracy: {routing}")

    if report.isolation_leaks or report.supersede_failures:
        lines += ["", "Gate failures"]
        lines += [f"  leak: {leak}" for leak in report.isolation_leaks]
        lines += [f"  supersede: {failure}" for failure in report.supersede_failures]

    failed = [r for r in report.results if not r.passed]
    if failed:
        lines += ["", f"Failed questions ({len(failed)}/{len(report.results)})"]
        for r in failed:
            q = r.question
            lines.append(f"  {q.id} [{q.category}] {q.question}")
            if r.missing:
                lines.append(f"       missing:  {', '.join(r.missing)}")
            if r.excluded_hits:
                lines.append(f"       excluded but returned:  {', '.join(r.excluded_hits)}")
            if r.leaked:
                lines.append(f"       LEAKED:   {', '.join(r.leaked)}")

    lines += ["", "PASS" if report.passed(require_retrieval) else "FAIL"]
    return "\n".join(lines)


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _mark(ok: bool) -> str:
    return "ok  " if ok else "FAIL"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mutable eval against a live API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("-k", type=int, default=5, help="top-k cutoff for retrieval metrics")
    parser.add_argument(
        "--require-retrieval",
        action="store_true",
        help="also fail the run when Recall/MRR are below the README's bars",
    )
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url) as client:
        report = evaluate(client, seed_all(client), k=args.k)
    print(format_report(report, args.require_retrieval))
    sys.exit(0 if report.passed(args.require_retrieval) else 1)


if __name__ == "__main__":
    main()
