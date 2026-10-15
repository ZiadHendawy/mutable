import pytest
from fastapi.testclient import TestClient

from app.main import app
from eval.read_data import load_persona
from eval.write_data import WriteError, write_persona

client = TestClient(app)


def _headers(tenant_id) -> dict[str, str]:
    return {"X-Tenant-Id": str(tenant_id)}


def test_writes_every_record_under_a_fresh_tenant() -> None:
    records = load_persona("maya").records
    written = write_persona(client, records)

    assert set(written.ids) == {r.key for r in records.all_records()}
    for key, id_ in written.ids.items():
        path = {"fact": "facts", "preference": "preferences", "episode": "episodes"}[
            records.record_type(key)
        ]
        response = client.get(f"/{path}/{id_}", headers=_headers(written.tenant_id))
        assert response.status_code == 200, key


def test_supersede_chain_written_with_real_history() -> None:
    written = write_persona(client, load_persona("maya").records)
    headers = _headers(written.tenant_id)

    old = client.get(f"/preferences/{written.ids['maya.pref.diet.v1']}", headers=headers).json()
    new = client.get(f"/preferences/{written.ids['maya.pref.diet.v2']}", headers=headers).json()
    assert old["valid_from"] == "2016-01-01T00:00:00Z"
    assert old["valid_to"] == new["valid_from"] == "2025-05-01T00:00:00Z"
    assert old["superseded_by"] == new["id"]


def test_each_run_gets_its_own_tenant() -> None:
    records = load_persona("maya").records
    first = write_persona(client, records)
    second = write_persona(client, records)

    assert first.tenant_id != second.tenant_id
    assert set(first.ids.values()).isdisjoint(second.ids.values())


def test_written_personas_are_isolated() -> None:
    maya = write_persona(client, load_persona("maya").records)
    jonas = write_persona(client, load_persona("jonas").records)

    visible_to_jonas = client.get("/facts", headers=_headers(jonas.tenant_id)).json()
    assert {f["id"] for f in visible_to_jonas}.isdisjoint(str(i) for i in maya.ids.values())


def test_rejected_record_raises_with_its_key() -> None:
    records = load_persona("jonas").records
    # Assignment isn't validated, so this slips past read_data.py's checks and
    # simulates the API refusing a record.
    records.facts[0].confidence = 5.0

    with pytest.raises(WriteError, match="jonas.fact.lives_in_munich"):
        write_persona(client, records)
