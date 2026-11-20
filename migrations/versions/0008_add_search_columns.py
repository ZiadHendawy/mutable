"""add search columns

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15 14:47:20.800989

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("memory_facts", "memory_preferences", "memory_episodes")

# The size of app.embeddings.DIMENSION today, written out rather than imported: a migration
# records the schema as it was, so a later change of model gets a migration of its own.
DIMENSION = 384


def upgrade() -> None:
    for table in TABLES:
        # The API stores each new row's vector. Rows that already exist are left without one.
        op.add_column(table, sa.Column("embedding", Vector(DIMENSION), nullable=True))
        # Postgres computes this from content, for existing rows too, and keeps it up to date.
        op.add_column(
            table,
            sa.Column(
                "content_words",
                postgresql.TSVECTOR(),
                sa.Computed("to_tsvector('english', content)", persisted=True),
                nullable=False,
            ),
        )
        # GIN is Postgres's index for "which rows contain this word". There's no index on
        # embedding: search compares the question with every vector the tenant has, which
        # is exact and fast at this size (docs/design.md, gap 4.9).
        op.create_index(
            f"ix_{table}_content_words", table, ["content_words"], postgresql_using="gin"
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_content_words", table_name=table)
        op.drop_column(table, "content_words")
        op.drop_column(table, "embedding")
