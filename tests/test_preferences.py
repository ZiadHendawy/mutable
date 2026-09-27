from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TENANT_A = "88888888-8888-8888-8888-888888888888"
TENANT_B = "99999999-9999-9999-9999-999999999999"


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


def _create(tenant_id: str, **overrides: object) -> dict:
    payload = {"content": "prefers tea", "confidence": 0.8, "strength": 0.6}
    payload.update(overrides)
    response = client.post("/preferences", json=payload, headers=_headers(tenant_id))
    assert response.status_code == 201
    return response.json()


def test_create_and_get_preference() -> None:
    body = _create(TENANT_A)
    assert body["content"] == "prefers tea"
    assert body["strength"] == 0.6
    assert body["superseded_by"] is None
    assert body["valid_to"] is None

    get_response = client.get(f"/preferences/{body['id']}", headers=_headers(TENANT_A))
    assert get_response.status_code == 200


def test_list_preferences_scoped_to_tenant() -> None:
    _create(TENANT_A)
    response = client.get("/preferences", headers=_headers(TENANT_A))
    assert response.status_code == 200
    assert all(pref["tenant_id"] == TENANT_A for pref in response.json())


def test_preference_invisible_to_other_tenant() -> None:
    old = _create(TENANT_A)
    other_tenant_get = client.get(f"/preferences/{old['id']}", headers=_headers(TENANT_B))
    assert other_tenant_get.status_code == 404


def test_supersede_closes_old_and_links_to_new() -> None:
    old = _create(TENANT_A, content="prefers tea")
    new = _create(TENANT_A, content="prefers coffee", supersedes=old["id"])

    assert new["superseded_by"] is None
    assert new["valid_to"] is None

    old_after = client.get(f"/preferences/{old['id']}", headers=_headers(TENANT_A)).json()
    assert old_after["superseded_by"] == new["id"]
    assert old_after["valid_to"] is not None

    # The list (currently-valid only) should show the new one, not the old.
    current = client.get("/preferences", headers=_headers(TENANT_A)).json()
    current_ids = {pref["id"] for pref in current}
    assert new["id"] in current_ids
    assert old["id"] not in current_ids


def test_supersede_already_closed_preference_conflicts() -> None:
    old = _create(TENANT_A)
    _create(TENANT_A, supersedes=old["id"])

    response = client.post(
        "/preferences",
        json={"content": "third", "confidence": 0.5, "strength": 0.0, "supersedes": old["id"]},
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 409


def test_supersede_nonexistent_preference_not_found() -> None:
    response = client.post(
        "/preferences",
        json={
            "content": "x",
            "confidence": 0.5,
            "strength": 0.0,
            "supersedes": "00000000-0000-0000-0000-000000000000",
        },
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 404


def test_cannot_supersede_another_tenants_preference() -> None:
    tenant_a_pref = _create(TENANT_A)
    response = client.post(
        "/preferences",
        json={
            "content": "hijack attempt",
            "confidence": 0.5,
            "strength": 0.0,
            "supersedes": tenant_a_pref["id"],
        },
        headers=_headers(TENANT_B),
    )
    assert response.status_code == 404


def test_delete_preference() -> None:
    pref = _create(TENANT_A)
    delete_response = client.delete(f"/preferences/{pref['id']}", headers=_headers(TENANT_A))
    assert delete_response.status_code == 204
    assert client.get(f"/preferences/{pref['id']}", headers=_headers(TENANT_A)).status_code == 404


def test_create_preference_rejects_out_of_range_strength() -> None:
    response = client.post(
        "/preferences",
        json={"content": "x", "confidence": 0.5, "strength": 2.0},
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 422


def test_create_preference_defaults_valid_from_to_now() -> None:
    body = _create(TENANT_A)
    assert body["valid_from"] is not None


def test_backdated_supersede_closes_old_at_new_valid_from() -> None:
    old = _create(TENANT_A, content="vegetarian", valid_from="2018-01-01T00:00:00Z")
    new = _create(
        TENANT_A, content="pescatarian", valid_from="2025-04-01T00:00:00Z", supersedes=old["id"]
    )
    assert new["valid_from"] == "2025-04-01T00:00:00Z"

    old_after = client.get(f"/preferences/{old['id']}", headers=_headers(TENANT_A)).json()
    assert old_after["valid_from"] == "2018-01-01T00:00:00Z"
    # Windows tile exactly: the old one ends where the new one begins.
    assert old_after["valid_to"] == new["valid_from"]
    assert old_after["superseded_by"] == new["id"]


def test_supersede_rejects_new_valid_from_before_old() -> None:
    old = _create(TENANT_A, valid_from="2025-01-01T00:00:00Z")
    response = client.post(
        "/preferences",
        json={
            "content": "earlier",
            "confidence": 0.5,
            "strength": 0.0,
            "valid_from": "2024-01-01T00:00:00Z",
            "supersedes": old["id"],
        },
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 422

    # Rejected write is rolled back: the old record is still open.
    old_after = client.get(f"/preferences/{old['id']}", headers=_headers(TENANT_A)).json()
    assert old_after["valid_to"] is None


def test_delete_preference_that_replaced_another_conflicts() -> None:
    old = _create(TENANT_A, content="tea")
    new = _create(TENANT_A, content="coffee", supersedes=old["id"])

    response = client.delete(f"/preferences/{new['id']}", headers=_headers(TENANT_A))
    assert response.status_code == 409
    assert old["id"] in response.json()["detail"]
    # Refused means refused: both versions and their link are intact.
    assert client.get(f"/preferences/{new['id']}", headers=_headers(TENANT_A)).status_code == 200
    old_after = client.get(f"/preferences/{old['id']}", headers=_headers(TENANT_A)).json()
    assert old_after["superseded_by"] == new["id"]


def test_delete_oldest_version_of_a_chain_is_allowed() -> None:
    old = _create(TENANT_A, content="tea")
    new = _create(TENANT_A, content="coffee", supersedes=old["id"])

    assert client.delete(f"/preferences/{old['id']}", headers=_headers(TENANT_A)).status_code == 204
    assert client.get(f"/preferences/{old['id']}", headers=_headers(TENANT_A)).status_code == 404
    assert client.get(f"/preferences/{new['id']}", headers=_headers(TENANT_A)).status_code == 200
