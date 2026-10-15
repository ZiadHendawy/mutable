import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.embeddings import DIMENSION

# Every memory table has two columns for search, both made from content:
# - embedding: the content as a vector (see app/embeddings.py). The endpoint that creates a
#   row fills it in. It's nullable because rows written before migration 0008 have none.
# - content_words: the content's words, for full-text search. Postgres computes it from
#   content and keeps it up to date. "english" reduces each word to its base form ("lives"
#   becomes "live") and leaves out common words like "in".
CONTENT_WORDS = "to_tsvector('english', content)"


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryFact(Base):
    __tablename__ = "memory_facts"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_memory_facts_confidence_range"
        ),
        Index("ix_memory_facts_content_words", "content_words", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("tenants.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSION))
    content_words: Mapped[str] = mapped_column(TSVECTOR, Computed(CONTENT_WORDS, persisted=True))


class MemoryPreference(Base):
    __tablename__ = "memory_preferences"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_memory_preferences_confidence_range"
        ),
        CheckConstraint(
            "strength >= -1 AND strength <= 1", name="ck_memory_preferences_strength_range"
        ),
        Index("ix_memory_preferences_content_words", "content_words", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("tenants.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("memory_preferences.id")
    )
    source: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSION))
    content_words: Mapped[str] = mapped_column(TSVECTOR, Computed(CONTENT_WORDS, persisted=True))


class MemoryEpisode(Base):
    __tablename__ = "memory_episodes"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_memory_episodes_confidence_range"
        ),
        CheckConstraint(
            "event_time_end IS NULL OR event_time_end >= event_time",
            name="ck_memory_episodes_time_order",
        ),
        Index("ix_memory_episodes_content_words", "content_words", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("tenants.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    event_time_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSION))
    content_words: Mapped[str] = mapped_column(TSVECTOR, Computed(CONTENT_WORDS, persisted=True))
