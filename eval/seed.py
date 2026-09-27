"""Seed a persona's records into a running API, as a fresh tenant.

    python -m eval.seed maya jonas [--base-url http://localhost:8000]

Prints, per persona, the new tenant id and the key -> id map the harness needs to
score answers (the API assigns ids; the dataset only knows keys).
"""

import argparse
import json
import uuid
from dataclasses import dataclass

import httpx

from eval.dataset import PersonaRecords, load_persona


@dataclass
class SeededPersona:
    tenant_id: uuid.UUID
    ids: dict[str, uuid.UUID]  # dataset key -> id the API assigned


class SeedError(Exception):
    pass


def seed_persona(client: httpx.Client, records: PersonaRecords) -> SeededPersona:
    """POST every record through the public API under a brand-new tenant.

    Goes through the API rather than the database on purpose: the eval should
    exercise the same write path (validation, supersede handling, RLS) a real
    caller would.
    """
    tenant_id = uuid.uuid4()
    headers = {"X-Tenant-Id": str(tenant_id)}
    ids: dict[str, uuid.UUID] = {}

    def post(path: str, key: str, payload: dict) -> None:
        response = client.post(path, json=payload, headers=headers)
        if response.status_code != 201:
            raise SeedError(f"{key}: POST {path} -> {response.status_code} {response.text}")
        ids[key] = uuid.UUID(response.json()["id"])

    for fact in records.facts:
        post("/facts", fact.key, _payload(fact))

    # File order matters: the dataset guarantees a superseded preference appears
    # before its replacement, so its id is already known here.
    for pref in records.preferences:
        payload = _payload(pref, exclude={"supersedes"})
        if pref.supersedes is not None:
            payload["supersedes"] = str(ids[pref.supersedes])
        post("/preferences", pref.key, payload)

    for episode in records.episodes:
        post("/episodes", episode.key, _payload(episode))

    return SeededPersona(tenant_id=tenant_id, ids=ids)


def _payload(record, exclude: set[str] = frozenset()) -> dict:
    return record.model_dump(mode="json", exclude={"key", *exclude}, exclude_none=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("personas", nargs="+", help="directory names under eval/data/")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    # Validate every dataset before writing anything, so a bad file can't leave
    # a half-seeded run behind.
    datasets = {name: load_persona(name) for name in args.personas}

    out = {}
    with httpx.Client(base_url=args.base_url) as client:
        for name, persona in datasets.items():
            seeded = seed_persona(client, persona.records)
            out[name] = {
                "tenant_id": str(seeded.tenant_id),
                "ids": {key: str(id_) for key, id_ in seeded.ids.items()},
            }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
