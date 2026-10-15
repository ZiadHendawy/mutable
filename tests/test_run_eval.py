import pytest
from fastapi.testclient import TestClient

from app.main import app
from eval.run_eval import (
    EvalTenant,
    Retrieved,
    check_isolation,
    check_supersede,
    evaluate,
    format_report,
    write_all,
)

client = TestClient(app)


@pytest.fixture(scope="module")
def tenants() -> list[EvalTenant]:
    # Shared by the read-only tests; tests that mutate state write their own.
    return write_all(client)


def _maya(tenants: list[EvalTenant]) -> EvalTenant:
    return next(t for t in tenants if t.name == "maya")


def _retriever(pick):
    """Build a retriever from pick(question) -> (keys, route), for Maya's questions."""

    def retrieve(tenants, client_, tenant_id, text):
        maya = _maya(tenants)
        questions = [*maya.persona.questions, *maya.persona.heldout]
        question = next(q for q in questions if q.question == text)
        keys, route = pick(maya, question)
        ids = [maya.written.ids.get(k) or _jonas_id(tenants, k) for k in keys]
        return Retrieved(ids=ids, route=route)

    return retrieve


def _jonas_id(tenants, key):
    return next(t for t in tenants if t.name == "jonas").written.ids[key]


def test_clean_run_passes_gates_with_no_search(tenants) -> None:
    report = evaluate(client, tenants)

    assert report.isolation_leaks == []
    assert report.isolation_probes > 0
    assert report.supersede_failures == []
    assert len(report.results) == 75
    assert len(report.heldout) == 20
    assert report.recall == 0.0 and report.mrr == 0.0
    assert report.passed()
    assert not report.passed(require_retrieval=True)


def test_oracle_retriever_scores_perfectly(tenants) -> None:
    oracle = _retriever(lambda maya, q: (q.expected, maya.persona.expected_route(q)))
    report = evaluate(client, tenants, lambda *a: oracle(tenants, *a))

    assert report.recall == 1.0 and report.mrr == 1.0
    assert all(r.passed and r.route_ok for r in [*report.results, *report.heldout])
    assert report.passed(require_retrieval=True)
    assert "Routing accuracy: 1.00" in format_report(report)


def test_leaked_result_fails_the_gate(tenants) -> None:
    leaky = _retriever(lambda maya, q: ([*q.expected, "jonas.fact.lives_in_munich"], None))
    report = evaluate(client, tenants, lambda *a: leaky(tenants, *a))

    assert report.retrieval_leaks == 95  # 75 main + 20 held-out
    assert not report.passed()
    text = format_report(report)
    assert "LEAKED:   jonas.fact.lives_in_munich" in text
    assert "h001  LEAKED:   jonas.fact.lives_in_munich" in text


def test_heldout_is_gated_but_never_itemized(tenants) -> None:
    maya = _maya(tenants)
    main_only = _retriever(
        lambda maya, q: (q.expected if q.id.startswith("q") else [], maya.persona.expected_route(q))
    )
    report = evaluate(client, tenants, lambda *a: main_only(tenants, *a))

    # Perfect on the main set, nothing on held-out: the bars still fail.
    assert report.recall == 1.0 and report.mrr == 1.0
    assert not report.heldout_meets_bars
    assert report.passed()
    assert not report.passed(require_retrieval=True)

    text = format_report(report, require_retrieval=True)
    assert "held-out FAIL" in text
    for q in maya.persona.heldout:
        assert q.id not in text
        assert q.question not in text
        assert all(key not in text for key in q.expected)


def test_excluded_record_in_results_fails_question(tenants) -> None:
    stale = _retriever(lambda maya, q: ([*q.expected, *q.must_exclude], None))
    report = evaluate(client, tenants, lambda *a: stale(tenants, *a))

    q001 = next(r for r in report.results if r.question.id == "q001")
    assert q001.excluded_hits == ["maya.pref.diet.v1"]
    assert not q001.passed
    # Recall alone would call this perfect; the exclusion is what catches it.
    assert q001.recall == 1.0


def test_supersede_check_catches_a_closed_current_preference() -> None:
    maya = _maya(write_all(client, ["maya"]))
    # Close the current diet preference behind the data files' back.
    client.post(
        "/preferences",
        json={
            "content": "vegan",
            "confidence": 0.9,
            "strength": 0.9,
            "supersedes": str(maya.written.ids["maya.pref.diet.v2"]),
        },
        headers=maya.headers,
    )
    failures = check_supersede(client, maya)

    assert "maya: maya.pref.diet.v2 should be current but is closed" in failures
    assert "maya: q001: expected maya.pref.diet.v2 is not current" in failures


def test_isolation_check_catches_a_shared_tenant(tenants) -> None:
    maya = _maya(tenants)
    # An "other" tenant that is secretly the same tenant must see everything.
    impostor = EvalTenant("impostor", maya.persona, maya.written)
    leaks, _ = check_isolation(client, [maya, impostor])

    assert leaks
    assert any("impostor got 200 for maya's maya.pref.diet.v1" == leak for leak in leaks)
