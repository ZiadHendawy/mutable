"""enable row-level security

Revision ID: 41752e304b66
Revises: c6754f9c024c
Create Date: 2026-08-29 07:44:40.200793

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '41752e304b66'
down_revision: str | None = 'c6754f9c024c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tenants checks its own id; the memory tables check their tenant_id FK.
# No missing_ok on current_setting: an unset app.tenant_id errors loudly
# rather than silently matching nothing.
TABLE_CHECKS = {
    "tenants": "id = current_setting('app.tenant_id')::uuid",
    "memory_facts": "tenant_id = current_setting('app.tenant_id')::uuid",
    "memory_preferences": "tenant_id = current_setting('app.tenant_id')::uuid",
    "memory_episodes": "tenant_id = current_setting('app.tenant_id')::uuid",
}


def upgrade() -> None:
    for table, check in TABLE_CHECKS.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Redundant today (the owner is also a superuser, which FORCE can't
        # override anyway) but cheap insurance if ownership ever changes.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"FOR ALL USING ({check}) WITH CHECK ({check})"
        )


def downgrade() -> None:
    for table in TABLE_CHECKS:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
