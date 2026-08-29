import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.main import app

client = TestClient(app)

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())

TABLES = ("memory_facts", "memory_preferences", "memory_episodes")


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


def _seed_tenant(tenant_id: str) -> None:
    assert (
        client.post(
            "/facts", json={"content": "a fact", "confidence": 0.9}, headers=_headers(tenant_id)
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/preferences",
            json={"content": "a preference", "confidence": 0.8, "strength": 0.5},
            headers=_headers(tenant_id),
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/episodes",
            json={
                "content": "an episode",
                "confidence": 0.7,
                "event_time": "2026-03-04T14:00:00Z",
            },
            headers=_headers(tenant_id),
        ).status_code
        == 201
    )


def test_direct_postgres_session_enforces_tenant_isolation() -> None:
    # Seed real rows for two tenants through the actual API -- not raw SQL.
    _seed_tenant(TENANT_A)
    _seed_tenant(TENANT_B)

    # Bypass the API entirely: connect straight to Postgres as the same
    # restricted role the running API itself uses (settings.database_url,
    # not the migration superuser), and prove isolation holds at the
    # database layer for all three memory types.
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": TENANT_A})
        for table in TABLES:
            tenant_ids = {
                str(row) for row in conn.execute(text(f"SELECT tenant_id FROM {table}")).scalars()
            }
            assert TENANT_A in tenant_ids
            assert TENANT_B not in tenant_ids

        conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": TENANT_B})
        for table in TABLES:
            tenant_ids = {
                str(row) for row in conn.execute(text(f"SELECT tenant_id FROM {table}")).scalars()
            }
            assert TENANT_B in tenant_ids
            assert TENANT_A not in tenant_ids
