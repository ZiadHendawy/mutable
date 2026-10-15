import pytest

from eval.read_data import load_persona
from eval.write_data import PATHS, WriteError, write_persona


def test_writes_every_record_under_a_fresh_tenant(client) -> None:
    persona = load_persona("maya")
    written = write_persona(client, "maya", persona)

    records = persona.records
    assert set(written.ids) == {r.key for r in records.all_records()}
    for key, id_ in written.ids.items():
        path = PATHS[records.record_type(key)]
        response = client.get(f"{path}/{id_}", headers=written.headers)
        assert response.status_code == 200, key


def test_supersede_chain_written_with_real_history(client) -> None:
    written = write_persona(client, "maya", load_persona("maya"))

    def get(key: str) -> dict:
        return client.get(f"/preferences/{written.ids[key]}", headers=written.headers).json()

    old, new = get("maya.pref.diet.v1"), get("maya.pref.diet.v2")
    assert old["valid_from"] == "2016-01-01T00:00:00Z"
    assert old["valid_to"] == new["valid_from"] == "2025-05-01T00:00:00Z"
    assert old["superseded_by"] == new["id"]


def test_each_run_gets_its_own_tenant(client) -> None:
    maya = load_persona("maya")
    first = write_persona(client, "maya", maya)
    second = write_persona(client, "maya", maya)

    assert first.tenant_id != second.tenant_id
    assert set(first.ids.values()).isdisjoint(second.ids.values())


def test_written_personas_are_isolated(client) -> None:
    maya = write_persona(client, "maya", load_persona("maya"))
    jonas = write_persona(client, "jonas", load_persona("jonas"))

    visible_to_jonas = client.get("/facts", headers=jonas.headers).json()
    assert {f["id"] for f in visible_to_jonas}.isdisjoint(str(i) for i in maya.ids.values())


def test_rejected_record_raises_with_its_key(client) -> None:
    jonas = load_persona("jonas")
    # Assignment isn't validated, so this slips past read_data.py's checks and
    # simulates the API refusing a record.
    jonas.records.facts[0].confidence = 5.0

    with pytest.raises(WriteError, match="jonas.fact.lives_in_munich"):
        write_persona(client, "jonas", jonas)
