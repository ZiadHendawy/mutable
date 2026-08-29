from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


def _create(tenant_id: str, **overrides: object) -> dict:
    payload = {
        "content": "interviewed at Acme",
        "confidence": 0.9,
        "event_time": "2026-03-04T14:00:00Z",
    }
    payload.update(overrides)
    response = client.post("/episodes", json=payload, headers=_headers(tenant_id))
    assert response.status_code == 201
    return response.json()


def test_create_and_get_episode() -> None:
    body = _create(TENANT_A)
    assert body["content"] == "interviewed at Acme"
    assert body["event_time"] == "2026-03-04T14:00:00Z"
    assert body["event_time_end"] is None

    get_response = client.get(f"/episodes/{body['id']}", headers=_headers(TENANT_A))
    assert get_response.status_code == 200


def test_create_episode_with_duration() -> None:
    body = _create(
        TENANT_A,
        content="at a conference",
        event_time="2026-03-03T09:00:00Z",
        event_time_end="2026-03-05T18:00:00Z",
    )
    assert body["event_time_end"] == "2026-03-05T18:00:00Z"


def test_list_episodes_scoped_to_tenant() -> None:
    _create(TENANT_A)
    response = client.get("/episodes", headers=_headers(TENANT_A))
    assert response.status_code == 200
    assert all(ep["tenant_id"] == TENANT_A for ep in response.json())


def test_episode_invisible_to_other_tenant() -> None:
    episode = _create(TENANT_A)
    other_tenant_get = client.get(f"/episodes/{episode['id']}", headers=_headers(TENANT_B))
    assert other_tenant_get.status_code == 404


def test_delete_episode() -> None:
    episode = _create(TENANT_A)
    delete_response = client.delete(f"/episodes/{episode['id']}", headers=_headers(TENANT_A))
    assert delete_response.status_code == 204
    assert client.get(f"/episodes/{episode['id']}", headers=_headers(TENANT_A)).status_code == 404


def test_create_episode_rejects_out_of_range_confidence() -> None:
    response = client.post(
        "/episodes",
        json={"content": "x", "confidence": 1.5, "event_time": "2026-03-04T14:00:00Z"},
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 422


def test_create_episode_rejects_end_before_start() -> None:
    response = client.post(
        "/episodes",
        json={
            "content": "x",
            "confidence": 0.5,
            "event_time": "2026-03-04T14:00:00Z",
            "event_time_end": "2026-03-04T10:00:00Z",
        },
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 422


def test_create_episode_requires_event_time() -> None:
    response = client.post(
        "/episodes",
        json={"content": "x", "confidence": 0.5},
        headers=_headers(TENANT_A),
    )
    assert response.status_code == 422
