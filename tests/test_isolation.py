from sqlalchemy import create_engine, text

from app.settings import settings

TABLES = ("memory_facts", "memory_preferences", "memory_episodes")


def _write_rows(tenant) -> None:
    for path, payload in (
        ("/facts", {"content": "a fact", "confidence": 0.9}),
        ("/preferences", {"content": "a preference", "confidence": 0.8, "strength": 0.5}),
        (
            "/episodes",
            {"content": "an episode", "confidence": 0.7, "event_time": "2026-03-04T14:00:00Z"},
        ),
    ):
        assert tenant.post(path, json=payload).status_code == 201


def test_direct_postgres_session_enforces_tenant_isolation(tenant, other_tenant) -> None:
    # Write real rows for two tenants through the actual API -- not raw SQL.
    _write_rows(tenant)
    _write_rows(other_tenant)

    # Bypass the API entirely: connect straight to Postgres as the same
    # restricted role the running API itself uses (settings.database_url,
    # not the migration superuser), and prove isolation holds at the
    # database layer for all three memory types.
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        for me, them in ((tenant, other_tenant), (other_tenant, tenant)):
            conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": me.id})
            for table in TABLES:
                rows = conn.execute(text(f"SELECT tenant_id FROM {table}")).scalars()
                tenant_ids = {str(row) for row in rows}
                assert me.id in tenant_ids, table
                assert them.id not in tenant_ids, table
