"""Search: find the memories that best answer a question.

Two rankings of the caller's current records, merged into one:

- by meaning (`vector_search`): the question is embedded with the same model as the
  records, and records are ranked by how close their vectors are to the question's
- by words (`text_search`): Postgres full-text search, ranking records by how many of the
  question's words they contain, and how close together. It catches what meaning misses:
  names, places and rare words ("Theo", "Nordic Pay")

`hybrid_search` merges them with Reciprocal Rank Fusion. Both rank only the records in the
plan's time scope (app/search_plan.py): current versions, the versions true at a date, or
every version. Records of the kinds the plan expects then move ahead of the others.

Row-Level Security limits every query to the caller's own records, so nothing here filters
by tenant.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Select,
    Text,
    cast,
    func,
    literal,
    null,
    or_,
    select,
    union_all,
)
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.embeddings import Embedder
from app.search_plan import RecordType, SearchPlan
from app.tables import MemoryEpisode, MemoryFact, MemoryPreference

NOW = SearchPlan()  # the default plan: current versions only
Table = type[MemoryFact | MemoryPreference | MemoryEpisode]

TABLES: dict[RecordType, Table] = {
    "fact": MemoryFact,
    "preference": MemoryPreference,
    "episode": MemoryEpisode,
}

# How many records each ranking contributes to the merge. Far more than k, so a record
# ranked low by one method but high by the other still makes it in.
CANDIDATES = 50

# How much each ranking counts in the merge: meaning, then words. Words count for less: on
# its own, full-text search finds the right record far less often than vector search, since
# it can't tell a telling word ("Theo") from a common one ("prefers"). Its weight was
# tuned on the main eval questions only, never the held-out ones.
WEIGHTS = (1.0, 0.2)

# How much the "newest first" ranking counts, when the question asks for the most recent
# event. Less than meaning, so relevance still decides which events are candidates, and an
# unrelated recent event can't jump to the top. Tuned on the main eval questions only.
LATEST_WEIGHT = 0.3

# Reciprocal Rank Fusion's constant. Each ranking gives a record 1 / (RRF_K + its rank), so
# a larger constant flattens the gap between 1st and 2nd place. 60 is the value from the
# paper that introduced RRF (Cormack et al., 2009), and the usual default.
RRF_K = 60


@dataclass(frozen=True)
class Hit:
    """One search result: a record, and how well it matches the question."""

    id: uuid.UUID
    type: RecordType
    content: str
    score: float  # higher is better; what it measures depends on the ranking
    valid_from: datetime
    valid_to: datetime | None
    event_time: datetime | None  # episodes only


def hybrid_search(
    db: Session, embedder: Embedder, question: str, k: int, plan: SearchPlan = NOW
) -> list[Hit]:
    """The k records in the plan's scope best matching the question, by meaning and by
    words, best first. Records of the plan's types come before the rest.

    Each hit's score is its fused RRF score.
    """
    rankings = [
        vector_search(db, embedder, question, CANDIDATES, plan),
        text_search(db, question, CANDIDATES, plan),
    ]
    weights = list(WEIGHTS)
    if plan.latest:
        rankings.append(latest_episodes(db, CANDIDATES, plan))
        weights.append(LATEST_WEIGHT)
    fused = fuse(rankings, len(rankings) * CANDIDATES, weights)
    return planned_types_first(fused, plan.types)[:k]


def planned_types_first(hits: list[Hit], types: frozenset[RecordType]) -> list[Hit]:
    """The hits of the planned types, then the others, each group still in its order.

    A boost, not a filter: when the plan's guess about the question is wrong, the right
    record is ranked lower, but never hidden.
    """
    return [h for h in hits if h.type in types] + [h for h in hits if h.type not in types]


def fuse(rankings: list[list[Hit]], k: int, weights: Sequence[float]) -> list[Hit]:
    """Reciprocal Rank Fusion: merge rankings by position, not by score.

    The two rankings' scores aren't comparable (a cosine similarity, a text rank), but
    their positions are. A record gets weight / (RRF_K + rank) from each ranking it appears
    in, and the sum orders the result.

    Records with the same score in a ranking share a rank. Full-text scores tie often
    (every record matching one word of the question can score the same), and ranking ties
    by id would let the random ids decide, so results would change from run to run. Ties
    in the sum go to the record ranked higher by the first ranking, then the smaller id.
    """
    fused: dict[uuid.UUID, float] = defaultdict(float)
    first_rank: dict[uuid.UUID, int] = {}
    hits: dict[uuid.UUID, Hit] = {}
    for position, (ranking, weight) in enumerate(zip(rankings, weights, strict=True)):
        for rank, hit in zip(shared_ranks(ranking), ranking, strict=True):
            fused[hit.id] += weight / (RRF_K + rank)
            hits.setdefault(hit.id, hit)
            if position == 0:
                first_rank[hit.id] = rank
    unranked = len(rankings[0]) + 1 if rankings else 1
    best = sorted(fused, key=lambda i: (-fused[i], first_rank.get(i, unranked), i))[:k]
    return [replace(hits[id_], score=fused[id_]) for id_ in best]


def shared_ranks(ranking: list[Hit]) -> list[int]:
    """Each hit's rank, best first, with ties sharing the better rank: scores 0.9, 0.5,
    0.5, 0.1 rank 1, 2, 2, 4."""
    ranks = []
    for position, hit in enumerate(ranking, start=1):
        tied = ranks and hit.score == ranking[position - 2].score
        ranks.append(ranks[-1] if tied else position)
    return ranks


def vector_search(
    db: Session, embedder: Embedder, question: str, k: int, plan: SearchPlan = NOW
) -> list[Hit]:
    """The k records in scope whose meaning is closest to the question, best first.

    Each hit's score is the cosine similarity of the two vectors, from -1 to 1.
    """
    [question_vector] = embedder.embed([question])
    per_table = [
        # pgvector's <=> is cosine distance: 0 for the same direction, up to 2 for opposite
        # ones. 1 minus it is the cosine similarity.
        _in_scope(record_type, table, plan, 1 - table.embedding.cosine_distance(question_vector))
        # Rows written before migration 0008 have no vector, so can't be ranked.
        .where(table.embedding.is_not(None))
        for record_type, table in TABLES.items()
    ]
    return _top(db, per_table, k)


def text_search(db: Session, question: str, k: int, plan: SearchPlan = NOW) -> list[Hit]:
    """The k records in scope that best match the question's words, best first.

    Records that share no word with the question aren't returned. Each hit's score is
    Postgres's ts_rank_cd, which grows with the number of matching words and how close
    together they appear.
    """
    query = _any_word(question)
    per_table = [
        _in_scope(record_type, table, plan, func.ts_rank_cd(table.content_words, query))
        # @@ is "matches": the record contains at least one of the query's words.
        .where(table.content_words.op("@@")(query))
        for record_type, table in TABLES.items()
    ]
    return _top(db, per_table, k)


def latest_episodes(db: Session, k: int, plan: SearchPlan = NOW) -> list[Hit]:
    """The k most recent episodes in scope, newest first, whatever the question says.

    On its own this ranking knows nothing about the question; it's only ever merged with
    the two that do. Each hit's score is its event time, in seconds since 1970.
    """
    newest = _in_scope(
        "episode", MemoryEpisode, plan, func.extract("epoch", MemoryEpisode.event_time)
    )
    return _top(db, [newest], k)


def _any_word(question: str) -> ColumnElement:
    """A full-text query matching any of the question's words.

    plainto_tsquery reduces the question to its searchable words, the same way
    content_words was made ("What's Maya's diet these days?" becomes
    'maya' & 'diet' & 'day'), but joins them with & (all must match). A question has words
    no record contains ("what", "Maya"), so & would match almost nothing. Swapping & for |
    (any may match) leaves the ranking to decide which matches are best.
    """
    all_words = cast(func.plainto_tsquery("english", question), Text)
    return cast(func.replace(all_words, "&", "|"), TSQUERY)


def _in_scope(
    record_type: RecordType, table: Table, plan: SearchPlan, score: ColumnElement
) -> Select:
    """A table's records in the plan's time scope, as the columns every ranking returns,
    plus a score."""
    # Only episodes have an event time; the others fill the column with a typed NULL, so
    # all three SELECTs have the same columns and can be joined with UNION ALL.
    event_time = (
        table.event_time if table is MemoryEpisode else cast(null(), DateTime(timezone=True))
    )
    stmt = select(
        literal(record_type, Text).label("type"),
        table.id,
        table.content,
        table.valid_from,
        table.valid_to,
        event_time.label("event_time"),
        score.label("score"),
    )
    return stmt.where(*_time_filter(table, plan))


def _time_filter(table: Table, plan: SearchPlan) -> list[ColumnElement]:
    """Which of a table's records the plan's time scope keeps.

    Episodes are events, not states that hold for a while, so "as of" a date doesn't apply
    to them; they're only ever current or deleted. Instead, when the question names a
    period ("in October 2025"), an episode must overlap it.
    """
    if table is MemoryEpisode:
        return _episode_filter(plan)
    if plan.time == "history":
        return []  # every version
    if plan.time == "as_of":
        # The versions whose validity window contains the date. A window ends exactly where
        # its replacement's begins, so for a changed preference exactly one version matches.
        return [
            table.valid_from <= plan.as_of,
            or_(table.valid_to.is_(None), table.valid_to > plan.as_of),
        ]
    # "now": current versions only. A superseded preference has a valid_to.
    return [table.valid_to.is_(None)]


def _episode_filter(plan: SearchPlan) -> list[ColumnElement]:
    """Current episodes; when the question names a period, only those overlapping it."""
    conditions = [MemoryEpisode.valid_to.is_(None)]
    if plan.period is not None:
        # An event overlaps the period when it starts before the period ends and ends at or
        # after the period starts. A one-moment event has no end: it ends when it starts.
        ends = func.coalesce(MemoryEpisode.event_time_end, MemoryEpisode.event_time)
        conditions += [
            MemoryEpisode.event_time < plan.period.end,
            ends >= plan.period.start,
        ]
    return conditions


def _top(db: Session, per_table: list[Select], k: int) -> list[Hit]:
    """Join one SELECT per table into a single query, and return its k best rows."""
    candidates = union_all(*per_table).subquery()
    # id breaks ties, so the same data always gives the same order.
    stmt = select(candidates).order_by(candidates.c.score.desc(), candidates.c.id).limit(k)
    return [Hit(**row._mapping) for row in db.execute(stmt)]
