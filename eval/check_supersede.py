"""Supersede check: preference history is stored the way the data files describe it.

Reads the API's actual state, not the data files: every supersede chain is linked and tiles
in time (each old version closes exactly when its replacement starts), and every
preference-evolution question's expected / must_exclude records agree with that state.
"""

import uuid
from datetime import datetime

import httpx

from eval.read_data import Persona, Question
from eval.write_data import WrittenPersona


def check_supersede(client: httpx.Client, tenant: WrittenPersona) -> list[str]:
    records = tenant.persona.records
    ids = tenant.ids
    rows = {
        p.key: client.get(f"/preferences/{ids[p.key]}", headers=tenant.headers).json()
        for p in records.preferences
    }
    current = {
        uuid.UUID(r["id"]) for r in client.get("/preferences", headers=tenant.headers).json()
    }
    successor = records.successor_of()
    failures: list[str] = []

    for key, row in rows.items():
        nxt = successor.get(key)
        if nxt is None:
            if row["valid_to"] is not None or row["superseded_by"] is not None:
                failures.append(f"{key} should be current but is closed")
            if ids[key] not in current:
                failures.append(f"{key} is missing from GET /preferences")
            continue
        if row["superseded_by"] != str(ids[nxt]):
            failures.append(f"{key} should be superseded_by {nxt}")
        if row["valid_to"] is None or _dt(row["valid_to"]) != _dt(rows[nxt]["valid_from"]):
            failures.append(f"{key} should close exactly when {nxt} starts")
        if ids[key] in current:
            failures.append(f"{key} is superseded but still listed as current")

    for q in evolution_questions(tenant.persona):
        expected = [k for k in q.expected if k in rows]
        excluded = [k for k in q.must_exclude if k in rows]
        if q.category == "preference_current":
            failures += [
                f"{q.id}: expected {k} is not current" for k in expected if ids[k] not in current
            ]
            failures += [
                f"{q.id}: excluded {k} is still current" for k in excluded if ids[k] in current
            ]
        if q.as_of is not None:
            when = q.as_of.date()
            failures += [
                f"{q.id}: expected {k} was not valid on {when}"
                for k in expected
                if not _valid_at(rows[k], q.as_of)
            ]
            failures += [
                f"{q.id}: excluded {k} was valid on {when}"
                for k in excluded
                if _valid_at(rows[k], q.as_of)
            ]
    return [f"{tenant.name}: {f}" for f in failures]


def evolution_questions(persona: Persona) -> list[Question]:
    """The questions about a preference that changed: its current or an earlier version."""
    return [
        q
        for q in persona.questions
        if q.category in ("preference_current", "preference_historical")
    ]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _valid_at(row: dict, when: datetime) -> bool:
    if _dt(row["valid_from"]) > when:
        return False
    return row["valid_to"] is None or when < _dt(row["valid_to"])
