"""create the restricted app role

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-29 07:40:30.948925

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_TABLES = "tenants, memory_facts, memory_preferences, memory_episodes"


def upgrade() -> None:
    # Non-superuser role the running API connects as. RLS policies (next
    # migration) apply to it automatically, since it owns nothing and isn't
    # a superuser -- unlike the migration role, which bypasses RLS always.
    op.execute("CREATE ROLE mutable_app WITH LOGIN PASSWORD 'mutable_app'")
    op.execute("GRANT USAGE ON SCHEMA public TO mutable_app")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {APP_TABLES} TO mutable_app")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {APP_TABLES} FROM mutable_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM mutable_app")
    op.execute("DROP ROLE mutable_app")
