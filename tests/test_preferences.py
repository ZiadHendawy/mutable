def _create(tenant, **overrides: object) -> dict:
    payload = {"content": "prefers tea", "confidence": 0.8, "strength": 0.6}
    payload.update(overrides)
    response = tenant.post("/preferences", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_and_get_preference(tenant) -> None:
    body = _create(tenant)
    assert body["content"] == "prefers tea"
    assert body["strength"] == 0.6
    assert body["superseded_by"] is None
    assert body["valid_to"] is None

    assert tenant.get(f"/preferences/{body['id']}").status_code == 200


def test_list_preferences_scoped_to_tenant(tenant) -> None:
    pref = _create(tenant)
    response = tenant.get("/preferences")
    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [pref["id"]]


def test_preference_invisible_to_other_tenant(tenant, other_tenant) -> None:
    pref = _create(tenant)
    assert other_tenant.get(f"/preferences/{pref['id']}").status_code == 404


def test_supersede_closes_old_and_links_to_new(tenant) -> None:
    old = _create(tenant, content="prefers tea")
    new = _create(tenant, content="prefers coffee", supersedes=old["id"])

    assert new["superseded_by"] is None
    assert new["valid_to"] is None

    old_after = tenant.get(f"/preferences/{old['id']}").json()
    assert old_after["superseded_by"] == new["id"]
    assert old_after["valid_to"] is not None

    # The list (currently-valid only) shows the new one, not the old.
    current = [p["id"] for p in tenant.get("/preferences").json()]
    assert current == [new["id"]]


def test_supersede_already_closed_preference_conflicts(tenant) -> None:
    old = _create(tenant)
    _create(tenant, supersedes=old["id"])

    response = tenant.post(
        "/preferences",
        json={"content": "third", "confidence": 0.5, "strength": 0.0, "supersedes": old["id"]},
    )
    assert response.status_code == 409


def test_supersede_nonexistent_preference_not_found(tenant) -> None:
    response = tenant.post(
        "/preferences",
        json={
            "content": "x",
            "confidence": 0.5,
            "strength": 0.0,
            "supersedes": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404


def test_cannot_supersede_another_tenants_preference(tenant, other_tenant) -> None:
    pref = _create(tenant)
    response = other_tenant.post(
        "/preferences",
        json={
            "content": "hijack attempt",
            "confidence": 0.5,
            "strength": 0.0,
            "supersedes": pref["id"],
        },
    )
    assert response.status_code == 404


def test_delete_preference(tenant) -> None:
    pref = _create(tenant)
    assert tenant.delete(f"/preferences/{pref['id']}").status_code == 204
    assert tenant.get(f"/preferences/{pref['id']}").status_code == 404


def test_create_preference_rejects_out_of_range_strength(tenant) -> None:
    response = tenant.post(
        "/preferences", json={"content": "x", "confidence": 0.5, "strength": 2.0}
    )
    assert response.status_code == 422


def test_create_preference_defaults_valid_from_to_now(tenant) -> None:
    body = _create(tenant)
    assert body["valid_from"] is not None


def test_backdated_supersede_closes_old_at_new_valid_from(tenant) -> None:
    old = _create(tenant, content="vegetarian", valid_from="2018-01-01T00:00:00Z")
    new = _create(
        tenant, content="pescatarian", valid_from="2025-04-01T00:00:00Z", supersedes=old["id"]
    )
    assert new["valid_from"] == "2025-04-01T00:00:00Z"

    old_after = tenant.get(f"/preferences/{old['id']}").json()
    assert old_after["valid_from"] == "2018-01-01T00:00:00Z"
    # Windows tile exactly: the old one ends where the new one begins.
    assert old_after["valid_to"] == new["valid_from"]
    assert old_after["superseded_by"] == new["id"]


def test_supersede_rejects_new_valid_from_before_old(tenant) -> None:
    old = _create(tenant, valid_from="2025-01-01T00:00:00Z")
    response = tenant.post(
        "/preferences",
        json={
            "content": "earlier",
            "confidence": 0.5,
            "strength": 0.0,
            "valid_from": "2024-01-01T00:00:00Z",
            "supersedes": old["id"],
        },
    )
    assert response.status_code == 422

    # Rejected write is rolled back: the old record is still open.
    assert tenant.get(f"/preferences/{old['id']}").json()["valid_to"] is None


def test_delete_preference_that_replaced_another_conflicts(tenant) -> None:
    old = _create(tenant, content="tea")
    new = _create(tenant, content="coffee", supersedes=old["id"])

    response = tenant.delete(f"/preferences/{new['id']}")
    assert response.status_code == 409
    assert old["id"] in response.json()["detail"]
    # Refused means refused: both versions and their link are intact.
    assert tenant.get(f"/preferences/{new['id']}").status_code == 200
    assert tenant.get(f"/preferences/{old['id']}").json()["superseded_by"] == new["id"]


def test_delete_oldest_version_of_a_chain_is_allowed(tenant) -> None:
    old = _create(tenant, content="tea")
    new = _create(tenant, content="coffee", supersedes=old["id"])

    assert tenant.delete(f"/preferences/{old['id']}").status_code == 204
    assert tenant.get(f"/preferences/{old['id']}").status_code == 404
    assert tenant.get(f"/preferences/{new['id']}").status_code == 200
