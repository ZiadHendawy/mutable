"""Write personas into a running API, each as a fresh tenant.

    python -m eval.write_data maya jonas [--base-url http://localhost:8000]

Prints, per persona, the new tenant id and the id the API gave each record. The data files
only know records by key; the checks need those ids to find the records again.
"""

import argparse
import json
import uuid
from collections.abc import Collection
from dataclasses import dataclass

import httpx
from pydantic import BaseModel

from eval.read_data import Persona, RecordType, load_persona

PERSONAS = ["maya", "jonas"]

# Where each record type lives in the API.
PATHS: dict[RecordType, str] = {
    "fact": "/facts",
    "preference": "/preferences",
    "episode": "/episodes",
}


@dataclass
class WrittenPersona:
    """A persona as it now exists in the app: the fresh tenant it was written under, and the
    id the API assigned to each of its records."""

    name: str  # directory under eval/data/, e.g. "maya"
    persona: Persona
    tenant_id: uuid.UUID
    ids: dict[str, uuid.UUID]  # record key -> id the API assigned

    @property
    def key_of(self) -> dict[uuid.UUID, str]:
        """The reverse lookup: an id the API returned -> that record's key."""
        return {id_: key for key, id_ in self.ids.items()}

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Tenant-Id": str(self.tenant_id)}


class WriteError(Exception):
    pass


def write_all(client: httpx.Client, names: list[str] = PERSONAS) -> list[WrittenPersona]:
    # Load (and so validate) every persona before writing anything, so a bad file can't
    # leave a half-written run behind.
    personas = {name: load_persona(name) for name in names}
    return [write_persona(client, name, persona) for name, persona in personas.items()]


def write_persona(client: httpx.Client, name: str, persona: Persona) -> WrittenPersona:
    """POST every record through the public API under a brand-new tenant.

    Goes through the API rather than the database on purpose: the eval should
    exercise the same write path (validation, supersede handling, RLS) a real
    caller would.
    """
    tenant_id = uuid.uuid4()
    headers = {"X-Tenant-Id": str(tenant_id)}
    ids: dict[str, uuid.UUID] = {}

    def post(record_type: RecordType, key: str, payload: dict) -> None:
        path = PATHS[record_type]
        response = client.post(path, json=payload, headers=headers)
        if response.status_code != 201:
            raise WriteError(f"{key}: POST {path} -> {response.status_code} {response.text}")
        ids[key] = uuid.UUID(response.json()["id"])

    records = persona.records
    for fact in records.facts:
        post("fact", fact.key, _payload(fact))

    # File order matters: read_data.py guarantees a superseded preference appears
    # before its replacement, so its id is already known here.
    for pref in records.preferences:
        payload = _payload(pref, exclude={"supersedes"})
        if pref.supersedes is not None:
            payload["supersedes"] = str(ids[pref.supersedes])
        post("preference", pref.key, payload)

    for episode in records.episodes:
        post("episode", episode.key, _payload(episode))

    return WrittenPersona(name=name, persona=persona, tenant_id=tenant_id, ids=ids)


def _payload(record: BaseModel, exclude: Collection[str] = ()) -> dict:
    return record.model_dump(mode="json", exclude={"key", *exclude}, exclude_none=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write personas into a running API.")
    parser.add_argument("personas", nargs="+", help="directory names under eval/data/")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url) as client:
        written = write_all(client, args.personas)
    out = {
        w.name: {"tenant_id": str(w.tenant_id), "ids": {k: str(v) for k, v in w.ids.items()}}
        for w in written
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
