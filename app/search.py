"""Search: find the memories that best answer a question.

v1 (milestone 4, step 4) is vector search only. The question is embedded with the same
model as the records, and every current record of all three types is ranked by how close
its vector is to the question's. Row-Level Security limits the query to the caller's own
records, so nothing here filters by tenant.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, Text, cast, literal, null, select, union_all
from sqlalchemy.orm import Session

from app.embeddings import Embedder
from app.tables import MemoryEpisode, MemoryFact, MemoryPreference

RecordType = Literal["fact", "preference", "episode"]

TABLES: dict[RecordType, type[MemoryFact | MemoryPreference | MemoryEpisode]] = {
    "fact": MemoryFact,
    "preference": MemoryPreference,
    "episode": MemoryEpisode,
}


@dataclass(frozen=True)
class Hit:
    """One search result: a record, and how well it matches the question."""

    id: uuid.UUID
    type: RecordType
    content: str
    score: float  # cosine similarity, -1 to 1; higher is closer
    valid_from: datetime
    valid_to: datetime | None
    event_time: datetime | None  # episodes only


def vector_search(db: Session, embedder: Embedder, question: str, k: int) -> list[Hit]:
    """The k current records whose meaning is closest to the question, best first."""
    [question_vector] = embedder.embed([question])

    # One SELECT per table, glued into one query with UNION ALL, so a single ORDER BY ranks
    # all three types together. Each SELECT returns the same columns in the same order.
    per_table = []
    for record_type, table in TABLES.items():
        # Only episodes have an event time; the others fill the column with a typed NULL.
        event_time = (
            table.event_time if table is MemoryEpisode else cast(null(), DateTime(timezone=True))
        )
        per_table.append(
            select(
                literal(record_type, Text).label("type"),
                table.id,
                table.content,
                table.valid_from,
                table.valid_to,
                event_time.label("event_time"),
                # pgvector's <=> operator: cosine distance, 0 for the same direction, up to 2
                # for opposite ones.
                table.embedding.cosine_distance(question_vector).label("distance"),
            ).where(
                # Current versions only: a superseded preference has a valid_to.
                table.valid_to.is_(None),
                # Rows written before migration 0008 have no vector, so can't be ranked.
                table.embedding.is_not(None),
            )
        )
    candidates = union_all(*per_table).subquery()
    # id breaks ties, so the same data always gives the same order.
    stmt = select(candidates).order_by(candidates.c.distance, candidates.c.id).limit(k)

    return [
        Hit(
            id=row.id,
            type=row.type,
            content=row.content,
            score=1 - row.distance,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            event_time=row.event_time,
        )
        for row in db.execute(stmt)
    ]
