def test_whoami_returns_resolved_tenant(tenant) -> None:
    response = tenant.get("/whoami")
    assert response.status_code == 200
    assert response.json() == {"tenant_id": tenant.id}


def test_whoami_requires_tenant_header(client) -> None:
    response = client.get("/whoami")
    assert response.status_code == 422


def test_whoami_rejects_non_uuid_tenant_header(client) -> None:
    response = client.get("/whoami", headers={"X-Tenant-Id": "not-a-uuid"})
    assert response.status_code == 422
