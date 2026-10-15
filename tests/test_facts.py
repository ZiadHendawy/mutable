def test_create_and_get_fact(tenant) -> None:
    response = tenant.post("/facts", json={"content": "lives in London", "confidence": 0.9})
    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "lives in London"
    assert body["confidence"] == 0.9
    assert body["tenant_id"] == tenant.id
    assert body["valid_to"] is None
    assert body["id"]
    assert body["created_at"]

    get_response = tenant.get(f"/facts/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == body["id"]


def test_list_facts_scoped_to_tenant(tenant) -> None:
    tenant.post("/facts", json={"content": "fact one", "confidence": 0.5})
    response = tenant.get("/facts")
    assert response.status_code == 200
    facts = response.json()
    assert len(facts) == 1
    assert facts[0]["tenant_id"] == tenant.id


def test_fact_invisible_to_other_tenant(tenant, other_tenant) -> None:
    fact = tenant.post("/facts", json={"content": "first tenant only", "confidence": 0.8}).json()

    assert other_tenant.get(f"/facts/{fact['id']}").status_code == 404
    assert other_tenant.get("/facts").json() == []


def test_delete_fact(tenant) -> None:
    fact = tenant.post("/facts", json={"content": "to be deleted", "confidence": 0.5}).json()

    assert tenant.delete(f"/facts/{fact['id']}").status_code == 204
    assert tenant.get(f"/facts/{fact['id']}").status_code == 404


def test_create_fact_rejects_out_of_range_confidence(tenant) -> None:
    response = tenant.post("/facts", json={"content": "bad confidence", "confidence": 1.5})
    assert response.status_code == 422


def test_facts_require_tenant_header(client) -> None:
    response = client.get("/facts/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 422


def test_create_fact_with_backdated_valid_from(tenant) -> None:
    response = tenant.post(
        "/facts",
        json={
            "content": "lives in Lisbon",
            "confidence": 0.9,
            "valid_from": "2024-09-01T00:00:00Z",
        },
    )
    assert response.status_code == 201
    assert response.json()["valid_from"] == "2024-09-01T00:00:00Z"
