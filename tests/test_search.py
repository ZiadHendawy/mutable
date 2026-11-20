"""GET /search: ranks the caller's current records against the question.

The tests run with FakeEmbedder (tests/conftest.py), whose vectors are close exactly when
texts share words. So "closest in meaning" here means "shares the most words", which makes
every expected order something you can work out by reading the texts.
"""

import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.embeddings import FakeEmbedder
from app.search import vector_search

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


def test_records_without_a_vector_are_still_found_by_their_words(tenant) -> None:
    ids = _write(tenant)
    # Like a row written before migration 0008: no embedding.
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        db.execute(
            text("UPDATE memory_facts SET embedding = NULL WHERE id = :id"), {"id": ids["fact"]}
        )
        db.commit()
    assert ids["fact"] in {r["id"] for r in _search(tenant, "Lisbon")}
    # But not by meaning, which needs the vector.
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        hits = vector_search(db, FakeEmbedder(), "Lisbon", 10)
    assert ids["fact"] not in {str(h.id) for h in hits}


def test_vector_scores_are_cosine_similarities(tenant) -> None:
    ids = _write(tenant)
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        hits = vector_search(db, FakeEmbedder(), "Lisbon", 10)
    [question, fact] = FakeEmbedder().embed(["Lisbon", LISBON["content"]])
    expected = sum(a * b for a, b in zip(question, fact, strict=True))
    assert next(h.score for h in hits if str(h.id) == ids["fact"]) == pytest.approx(expected)


def test_rejects_bad_parameters(tenant) -> None:
    for params in ({"q": ""}, {"q": "tea", "k": 0}, {"q": "tea", "k": 51}, {}):
        assert tenant.get("/search", params=params).status_code == 422, params


def test_requires_a_tenant(client) -> None:
    assert client.get("/search", params={"q": "tea"}).status_code == 422
    headers = {"X-Tenant-Id": str(uuid.uuid4())}
    assert client.get("/search", params={"q": "tea"}, headers=headers).json()["results"] == []


def _diet_history(tenant) -> tuple[str, str]:
    """Vegetarian from 2016, pescatarian from May 2025. Returns (old id, new id)."""
    old = tenant.post(
        "/preferences",
        json={
            "content": "Is vegetarian",
            "confidence": 0.9,
            "strength": 0.9,
            "valid_from": "2016-01-01T00:00:00Z",
        },
    ).json()["id"]
    new = tenant.post(
        "/preferences",
        json={
            "content": "Is pescatarian",
            "confidence": 0.9,
            "strength": 0.9,
            "valid_from": "2025-05-01T00:00:00Z",
            "supersedes": old,
        },
    ).json()["id"]
    return old, new


def _search_with_plan(tenant, q: str) -> tuple[dict, list[str]]:
    response = tenant.get("/search", params={"q": q, "k": 50})
    assert response.status_code == 200, response.text
    body = response.json()
    return body["plan"], [r["id"] for r in body["results"]]


def test_a_question_about_now_gets_the_current_version(tenant) -> None:
    old, new = _diet_history(tenant)
    plan, ids = _search_with_plan(tenant, "Is she vegetarian these days?")
    assert (plan["time"], plan["as_of"]) == ("now", None)
    assert new in ids and old not in ids


def test_a_dated_question_gets_the_version_true_then(tenant) -> None:
    old, new = _diet_history(tenant)
    plan, ids = _search_with_plan(tenant, "Was she vegetarian in 2023?")
    assert (plan["time"], plan["as_of"]) == ("as_of", "2023-07-01T00:00:00Z")
    assert old in ids and new not in ids


def test_a_date_before_any_version_gets_neither(tenant) -> None:
    old, new = _diet_history(tenant)
    _, ids = _search_with_plan(tenant, "Was she vegetarian in 2010?")
    assert old not in ids and new not in ids


def test_a_history_question_gets_every_version(tenant) -> None:
    old, new = _diet_history(tenant)
    plan, ids = _search_with_plan(tenant, "How has her diet changed over time?")
    assert (plan["time"], plan["as_of"]) == ("history", None)
    assert old in ids and new in ids


def test_dated_questions_still_find_episodes(tenant) -> None:
    # Episodes are events, not states: "as of" a date never hides them. Their valid_from
    # is the write time, which a strict window would put after any past date.
    episode = tenant.post("/episodes", json=MARATHON).json()["id"]
    _, ids = _search_with_plan(tenant, "What did she run in October 2025?")
    assert episode in ids


def test_the_planned_types_come_first_but_nothing_is_hidden(tenant) -> None:
    ids = _write(tenant)
    response = tenant.get("/search", params={"q": "When did she run in Lisbon?"}).json()
    assert response["plan"]["types"] == ["episode"]
    results = [r["id"] for r in response["results"]]
    # The episode first; the Lisbon fact, a different type, still comes back after it.
    assert results[0] == ids["episode"]
    assert ids["fact"] in results


def test_the_plan_lists_its_types_sorted(tenant) -> None:
    response = tenant.get("/search", params={"q": "Where does she live?"}).json()
    assert response["plan"]["types"] == ["episode", "fact", "preference"]
