import pytest
from fastapi.testclient import TestClient

from app.main import app
from eval.harness import (
    Retrieved,
    SeededTenant,
    check_isolation,
    check_supersede,
    evaluate,
    format_report,
    seed_all,
)

client = TestClient(app)


@pytest.fixture(scope="module")
def tenants() -> list[SeededTenant]:
    # Shared by the read-only tests; tests that mutate state seed their own.
    return seed_all(client)


def _maya(tenants: list[SeededTenant]) -> SeededTenant:
    return next(t for t in tenants if t.name == "maya")


def _retriever(pick):
    """Build a retriever from pick(question) -> (keys, route), for Maya's questions."""

    def retrieve(tenants, client_, tenant_id, text):
        maya = _maya(tenants)
        question = next(q for q in maya.persona.questions if q.question == text)
        keys, route = pick(maya, question)
        ids = [maya.seeded.ids.get(k) or _jonas_id(tenants, k) for k in keys]
        return Retrieved(ids=ids, route=route)

    return retrieve


def _jonas_id(tenants, key):
    return next(t for t in tenants if t.name == "jonas").seeded.ids[key]


def test_clean_run_passes_gates_with_no_search(tenants) -> None:
    report = evaluate(client, tenants)

    assert report.isolation_leaks == []
    assert report.isolation_probes > 0
    assert report.supersede_failures == []
    assert len(report.results) == 75
    assert report.recall == 0.0 and report.mrr == 0.0
    assert report.passed()
    assert not report.passed(require_retrieval=True)


def test_oracle_retriever_scores_perfectly(tenants) -> None:
    oracle = _retriever(lambda maya, q: (q.gold, maya.persona.expected_route(q)))
    report = evaluate(client, tenants, lambda *a: oracle(tenants, *a))

    assert report.recall == 1.0 and report.mrr == 1.0
    assert all(r.passed and r.route_ok for r in report.results)
    assert report.passed(require_retrieval=True)
    assert "Routing accuracy: 1.00" in format_report(report)


def test_leaked_result_fails_the_gate(tenants) -> None:
    leaky = _retriever(lambda maya, q: ([*q.gold, "jonas.fact.lives_in_munich"], None))
    report = evaluate(client, tenants, lambda *a: leaky(tenants, *a))

    assert report.retrieval_leaks == 75
    assert not report.passed()
    assert "LEAKED:   jonas.fact.lives_in_munich" in format_report(report)


def test_excluded_record_in_results_fails_question(tenants) -> None:
    stale = _retriever(lambda maya, q: ([*q.gold, *q.must_exclude], None))
    report = evaluate(client, tenants, lambda *a: stale(tenants, *a))

    q001 = next(r for r in report.results if r.question.id == "q001")
    assert q001.excluded_hits == ["maya.pref.diet.v1"]
    assert not q001.passed
    # Recall alone would call this perfect; the exclusion is what catches it.
    assert q001.recall == 1.0


def test_supersede_check_catches_a_closed_current_preference() -> None:
    maya = _maya(seed_all(client, ["maya"]))
    # Close the current diet preference behind the dataset's back.
    client.post(
        "/preferences",
        json={
            "content": "vegan",
            "confidence": 0.9,
            "strength": 0.9,
            "supersedes": str(maya.seeded.ids["maya.pref.diet.v2"]),
        },
        headers=maya.headers,
    )
    failures = check_supersede(client, maya)

    assert "maya: maya.pref.diet.v2 should be current but is closed" in failures
    assert "maya: q001: gold maya.pref.diet.v2 is not current" in failures


def test_isolation_check_catches_a_shared_tenant(tenants) -> None:
    maya = _maya(tenants)
    # An "other" tenant that is secretly the same tenant must see everything.
    impostor = SeededTenant("impostor", maya.persona, maya.seeded)
    leaks, _ = check_isolation(client, [maya, impostor])

    assert leaks
    assert any("impostor got 200 for maya's maya.pref.diet.v1" == leak for leak in leaks)
