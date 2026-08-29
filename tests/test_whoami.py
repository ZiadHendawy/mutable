from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TENANT_ID = "11111111-1111-1111-1111-111111111111"


def test_whoami_returns_resolved_tenant() -> None:
    response = client.get("/whoami", headers={"X-Tenant-Id": TENANT_ID})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": TENANT_ID}


def test_whoami_requires_tenant_header() -> None:
    response = client.get("/whoami")
    assert response.status_code == 422


def test_whoami_rejects_non_uuid_tenant_header() -> None:
    response = client.get("/whoami", headers={"X-Tenant-Id": "not-a-uuid"})
    assert response.status_code == 422
