def _create(tenant, **overrides: object) -> dict:
    payload = {
        "content": "interviewed at Acme",
        "confidence": 0.9,
        "event_time": "2026-03-04T14:00:00Z",
    }
    payload.update(overrides)
    response = tenant.post("/episodes", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_and_get_episode(tenant) -> None:
    body = _create(tenant)
    assert body["content"] == "interviewed at Acme"
    assert body["event_time"] == "2026-03-04T14:00:00Z"
    assert body["event_time_end"] is None

    assert tenant.get(f"/episodes/{body['id']}").status_code == 200


def test_create_episode_with_duration(tenant) -> None:
    body = _create(
        tenant,
        content="at a conference",
        event_time="2026-03-03T09:00:00Z",
        event_time_end="2026-03-05T18:00:00Z",
    )
    assert body["event_time_end"] == "2026-03-05T18:00:00Z"


def test_list_episodes_scoped_to_tenant(tenant) -> None:
    episode = _create(tenant)
    response = tenant.get("/episodes")
    assert response.status_code == 200
    assert [ep["id"] for ep in response.json()] == [episode["id"]]


def test_episode_invisible_to_other_tenant(tenant, other_tenant) -> None:
    episode = _create(tenant)
    assert other_tenant.get(f"/episodes/{episode['id']}").status_code == 404


def test_delete_episode(tenant) -> None:
    episode = _create(tenant)
    assert tenant.delete(f"/episodes/{episode['id']}").status_code == 204
    assert tenant.get(f"/episodes/{episode['id']}").status_code == 404


def test_create_episode_rejects_out_of_range_confidence(tenant) -> None:
    response = tenant.post(
        "/episodes",
        json={"content": "x", "confidence": 1.5, "event_time": "2026-03-04T14:00:00Z"},
    )
    assert response.status_code == 422


def test_create_episode_rejects_end_before_start(tenant) -> None:
    response = tenant.post(
        "/episodes",
        json={
            "content": "x",
            "confidence": 0.5,
            "event_time": "2026-03-04T14:00:00Z",
            "event_time_end": "2026-03-04T10:00:00Z",
        },
    )
    assert response.status_code == 422


def test_create_episode_requires_event_time(tenant) -> None:
    response = tenant.post("/episodes", json={"content": "x", "confidence": 0.5})
    assert response.status_code == 422


def test_create_episode_with_backdated_valid_from(tenant) -> None:
    body = _create(tenant, valid_from="2025-06-01T00:00:00Z")
    assert body["valid_from"] == "2025-06-01T00:00:00Z"
