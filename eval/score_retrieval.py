"""Retrieval scoring: ask every question, and compare the top k results with the expected
answers.

A retriever gets only what a real caller has -- the question text -- never the expected
answers. `api_search` asks the app's /search endpoint, as a real caller would; `no_search`
finds nothing, and is what the eval's own tests use to check the gates in isolation.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from eval.read_data import Question, RecordType
from eval.write_data import WrittenPersona


@dataclass
class Retrieved:
    ids: list[uuid.UUID]  # ranked, best first
    route: set[RecordType] | None = None  # types the router chose, if it reports them


# (client, tenant id, question text) -> ranked results.
Retriever = Callable[[httpx.Client, uuid.UUID, str], Retrieved]


# How many results api_search asks for: more than any cutoff the report uses, so `-k` can
# be raised without changing this.
SEARCH_LIMIT = 20


def no_search(client: httpx.Client, tenant_id: uuid.UUID, question: str) -> Retrieved:
    """Finds nothing: the baseline, for checking the eval's other gates on their own."""
    return Retrieved(ids=[])


def api_search(client: httpx.Client, tenant_id: uuid.UUID, question: str) -> Retrieved:
    """Asks GET /search, as the tenant, exactly as a real caller would."""
    response = client.get(
        "/search",
        params={"q": question, "k": SEARCH_LIMIT},
        headers={"X-Tenant-Id": str(tenant_id)},
    )
    response.raise_for_status()
    body = response.json()
    return Retrieved(
        ids=[uuid.UUID(result["id"]) for result in body["results"]],
        route=set(body["plan"]["types"]),
    )


@dataclass
class QuestionResult:
    question: Question
    missing: list[str]  # expected keys not in the top k
    excluded_hits: list[str]  # must_exclude keys that made the top k
    leaked: list[str]  # top-k results that belong to another tenant
    reciprocal_rank: float
    route_ok: bool | None  # None when the retriever doesn't report a route

    @property
    def recall(self) -> float:
        expected = self.question.expected
        return (len(expected) - len(self.missing)) / len(expected)

    @property
    def passed(self) -> bool:
        return not (self.missing or self.excluded_hits or self.leaked)


def score_all(
    client: httpx.Client, tenants: list[WrittenPersona], retriever: Retriever, k: int
) -> tuple[list[QuestionResult], list[QuestionResult]]:
    """Asks every persona's questions. Returns (main results, held-out results)."""
    results: list[QuestionResult] = []
    heldout: list[QuestionResult] = []
    for tenant in tenants:
        others = [t for t in tenants if t is not tenant]
        for questions, scored in (
            (tenant.persona.questions, results),
            (tenant.persona.heldout, heldout),
        ):
            for q in questions:
                retrieved = retriever(client, tenant.tenant_id, q.question)
                scored.append(score_question(q, retrieved, tenant, others, k))
    return results, heldout


def score_question(
    question: Question,
    retrieved: Retrieved,
    tenant: WrittenPersona,
    others: list[WrittenPersona],
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

    rank = next((i for i, key in enumerate(top_keys, 1) if key in question.expected), None)
    route_ok = None
    if retrieved.route is not None:
        route_ok = retrieved.route == tenant.persona.expected_route(question)
    return QuestionResult(
        question=question,
        missing=[key for key in question.expected if key not in top_keys],
        excluded_hits=[key for key in question.must_exclude if key in top_keys],
        leaked=leaked,
        reciprocal_rank=1 / rank if rank else 0.0,
        route_ok=route_ok,
    )
