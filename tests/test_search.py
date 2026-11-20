"""GET /search: ranks the caller's current records by closeness to the question.

The tests run with FakeEmbedder (tests/conftest.py), whose vectors are close exactly when
texts share words. So "closest in meaning" here means "shares the most words", which makes
every expected order something you can work out by reading the texts.
"""

import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.embeddings import FakeEmbedder

LISBON = {"content": "Lives in Lisbon", "confidence": 0.9}
TEA = {"content": "Prefers green tea in the afternoon", "confidence": 0.8, "strength": 0.7}
MARATHON = {
    "content": "Ran the Lisbon half-marathon",
    "confidence": 0.9,
    "event_time": "2025-10-12T09:00:00Z",
}


def _write(tenant) -> dict[str, str]:
    """One record of each type. Returns their ids by type."""
    return {
        "fact": tenant.post("/facts", json=LISBON).json()["id"],
        "preference": tenant.post("/preferences", json=TEA).json()["id"],
        "episode": tenant.post("/episodes", json=MARATHON).json()["id"],
    }


def _search(tenant, q: str, **params) -> list[dict]:
    response = tenant.get("/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_ranks_the_closest_record_first(tenant) -> None:
    ids = _write(tenant)
    results = _search(tenant, "green tea")
    assert results[0]["id"] == ids["preference"]
    assert results[0]["type"] == "preference"
    assert results[0]["content"] == TEA["content"]


def test_returns_every_type_best_first_with_scores(tenant) -> None:
    ids = _write(tenant)
    results = _search(tenant, "Lisbon")
    assert {r["id"] for r in results} == set(ids.values())
    # The two records that mention Lisbon outrank the one that doesn't.
    assert {r["id"] for r in results[:2]} == {ids["fact"], ids["episode"]}
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    # The score is the cosine similarity of the two fake vectors.
    [question, fact] = FakeEmbedder().embed(["Lisbon", LISBON["content"]])
    expected = sum(a * b for a, b in zip(question, fact, strict=True))
    assert next(r["score"] for r in results if r["id"] == ids["fact"]) == pytest.approx(expected)


def test_episodes_carry_their_event_time(tenant) -> None:
    ids = _write(tenant)
    by_id = {r["id"]: r for r in _search(tenant, "Lisbon")}
    assert by_id[ids["episode"]]["event_time"].startswith("2025-10-12T09:00:00")
    assert by_id[ids["fact"]]["event_time"] is None


def test_superseded_versions_are_left_out(tenant) -> None:
    old = tenant.post(
        "/preferences",
        json={"content": "Drinks coffee every morning", "confidence": 0.9, "strength": 0.8},
    ).json()["id"]
    new = tenant.post(
        "/preferences",
        json={
            "content": "Drinks matcha every morning, no coffee",
            "confidence": 0.9,
            "strength": 0.8,
            "supersedes": old,
        },
    ).json()["id"]
    ids = [r["id"] for r in _search(tenant, "coffee every morning")]
    assert ids == [new]


def test_never_returns_another_tenants_records(tenant, other_tenant) -> None:
    mine = _write(tenant)
    theirs = _write(other_tenant)
    ids = {r["id"] for r in _search(tenant, "Lives in Lisbon", k=50)}
    assert ids == set(mine.values())
    assert not ids & set(theirs.values())


def test_k_limits_the_results(tenant) -> None:
    _write(tenant)
    assert len(_search(tenant, "Lisbon", k=1)) == 1
    # The default is 5; this tenant has only 3 records.
    assert len(_search(tenant, "Lisbon")) == 3


def test_a_tenant_with_no_records_gets_no_results(tenant) -> None:
    assert _search(tenant, "anything") == []


def test_records_without_a_vector_are_skipped(tenant) -> None:
    ids = _write(tenant)
    # Like a row written before migration 0008: no embedding.
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        db.execute(
            text("UPDATE memory_facts SET embedding = NULL WHERE id = :id"), {"id": ids["fact"]}
        )
        db.commit()
    assert ids["fact"] not in {r["id"] for r in _search(tenant, "Lisbon")}


def test_rejects_bad_parameters(tenant) -> None:
    for params in ({"q": ""}, {"q": "tea", "k": 0}, {"q": "tea", "k": 51}, {}):
        assert tenant.get("/search", params=params).status_code == 422, params


def test_requires_a_tenant(client) -> None:
    assert client.get("/search", params={"q": "tea"}).status_code == 422
    headers = {"X-Tenant-Id": str(uuid.uuid4())}
    assert client.get("/search", params={"q": "tea"}, headers=headers).json() == {"results": []}
