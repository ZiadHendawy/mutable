from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TENANT_A = "44444444-4444-4444-4444-444444444444"
TENANT_B = "55555555-5555-5555-5555-555555555555"


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


def test_create_and_get_fact() -> None:
    response = client.post(
        "/facts",
        json={"content": "lives in London", "confidence": 0.9},
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "lives in London"
    assert body["confidence"] == 0.9
    assert body["tenant_id"] == TENANT_A
    assert body["valid_to"] is None
    assert body["id"]
    assert body["created_at"]

    fact_id = body["id"]
    get_response = client.get(f"/facts/{fact_id}", headers=_headers(TENANT_A))
    assert get_response.status_code == 200
    assert get_response.json()["id"] == fact_id


def test_list_facts_scoped_to_tenant() -> None:
    client.post(
        "/facts", json={"content": "fact one", "confidence": 0.5}, headers=_headers(TENANT_A)
    )
    response = client.get("/facts", headers=_headers(TENANT_A))
    assert response.status_code == 200
    facts = response.json()
    assert len(facts) >= 1
    assert all(fact["tenant_id"] == TENANT_A for fact in facts)


def test_fact_invisible_to_other_tenant() -> None:
    create_response = client.post(
        "/facts", json={"content": "tenant A only", "confidence": 0.8}, headers=_headers(TENANT_A)
    )
    fact_id = create_response.json()["id"]

    other_tenant_get = client.get(f"/facts/{fact_id}", headers=_headers(TENANT_B))
    assert other_tenant_get.status_code == 404

    other_tenant_list = client.get("/facts", headers=_headers(TENANT_B))
    assert all(fact["id"] != fact_id for fact in other_tenant_list.json())


def test_delete_fact() -> None:
    create_response = client.post(
        "/facts", json={"content": "to be deleted", "confidence": 0.5}, headers=_headers(TENANT_A)
    )
    fact_id = create_response.json()["id"]

    delete_response = client.delete(f"/facts/{fact_id}", headers=_headers(TENANT_A))
    assert delete_response.status_code == 204

    get_response = client.get(f"/facts/{fact_id}", headers=_headers(TENANT_A))
    assert get_response.status_code == 404


def test_create_fact_rejects_out_of_range_confidence() -> None:
    response = client.post(
        "/facts",
        json={"content": "bad confidence", "confidence": 1.5},
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 422


def test_facts_require_tenant_header() -> None:
    response = client.get("/facts/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 422
