"""The two rankings behind /search, and how they're merged.

text_search is plain Postgres full-text search, so its tests use real words. fuse is pure
Python, so its tests build rankings by hand.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import SessionLocal
from app.search import RRF_K, Hit, fuse, shared_ranks, text_search


def _session_for(tenant):
    db = SessionLocal()
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
    return db


def _fact(tenant, content: str) -> str:
    return tenant.post("/facts", json={"content": content, "confidence": 0.9}).json()["id"]


def test_text_search_finds_records_by_their_words(tenant) -> None:
    theo = _fact(tenant, "Her brother Theo lives in Vancouver")
    _fact(tenant, "Works as a product designer")
    with _session_for(tenant) as db:
        hits = text_search(db, "When did Theo last visit?", 10)
    # Only the record that shares a word: "When", "did" and "last" are too common to index.
    assert [str(h.id) for h in hits] == [theo]


def test_text_search_matches_word_forms(tenant) -> None:
    # "visits" and "visited" both reduce to "visit".
    visit = _fact(tenant, "Visits her parents every December")
    with _session_for(tenant) as db:
        assert [str(h.id) for h in text_search(db, "When was she visited?", 10)] == [visit]


def test_text_search_ranks_more_shared_words_higher(tenant) -> None:
    one = _fact(tenant, "Speaks conversational Mandarin")
    two = _fact(tenant, "Speaks Mandarin and is learning Portuguese")
    with _session_for(tenant) as db:
        hits = text_search(db, "Is she learning Mandarin?", 10)
    assert [str(h.id) for h in hits] == [two, one]


def test_text_search_with_no_searchable_words_finds_nothing(tenant) -> None:
    _fact(tenant, "Lives in Lisbon")
    with _session_for(tenant) as db:
        assert text_search(db, "What is it?", 10) == []


def _hit(n: int, score: float | None = None) -> Hit:
    """A made-up hit. Unless given a score, each gets its own, so there are no ties."""
    when = datetime(2026, 1, 1, tzinfo=UTC)
    return Hit(
        uuid.UUID(int=n), "fact", f"record {n}", -n if score is None else score, when, None, None
    )


def test_fuse_favors_records_both_rankings_found() -> None:
    a, b, c = _hit(1), _hit(2), _hit(3)
    # a is 1st by meaning only; b is 2nd in both.
    fused = fuse([[a, b], [c, b]], k=3, weights=[1.0, 1.0])
    assert [h.id for h in fused] == [b.id, a.id, c.id]
    assert fused[0].score == 2 / (RRF_K + 2)


def test_fuse_weights_each_ranking() -> None:
    a, c = _hit(1), _hit(3)
    # Both are 1st in their own ranking; the second ranking counts for less.
    fused = fuse([[a], [c]], k=2, weights=[1.0, 0.5])
    assert [h.id for h in fused] == [a.id, c.id]
    assert fused[1].score == 0.5 / (RRF_K + 1)


def test_fuse_cuts_at_k() -> None:
    a, b = _hit(1), _hit(2)
    assert len(fuse([[a, b]], k=1, weights=[1.0])) == 1


def test_tied_scores_share_a_rank() -> None:
    ranking = [_hit(1, 0.9), _hit(2, 0.5), _hit(3, 0.5), _hit(4, 0.1)]
    assert shared_ranks(ranking) == [1, 2, 2, 4]
    assert shared_ranks([]) == []


def test_ties_in_one_ranking_count_the_same() -> None:
    a, b = _hit(1, 0.5), _hit(2, 0.5)
    fused = fuse([[b, a]], k=2, weights=[1.0])
    assert fused[0].score == fused[1].score == 1 / (RRF_K + 1)


def test_fused_ties_go_to_the_first_rankings_order() -> None:
    a, b = _hit(1), _hit(2)
    # Each is 1st in one ranking, at equal weight: a tie, decided by the first ranking.
    assert [h.id for h in fuse([[b], [a]], k=2, weights=[1.0, 1.0])] == [b.id, a.id]
