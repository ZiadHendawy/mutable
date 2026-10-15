"""Isolation check: no persona can reach another persona's records.

Every record is requested by id, and every list endpoint is read, as every *other* tenant.
Anything but a 404 by id, or another tenant's record showing up in a list, is a leak.
"""

import uuid

import httpx

from eval.write_data import PATHS, WrittenPersona


def check_isolation(client: httpx.Client, tenants: list[WrittenPersona]) -> tuple[list[str], int]:
    """Returns (leaks, number of probes made)."""
    leaks: list[str] = []
    probes = 0
    for owner in tenants:
        owned = owner.key_of
        for other in tenants:
            if other is owner:
                continue
            for key, id_ in owner.ids.items():
                path = PATHS[owner.persona.records.record_type(key)]
                status = client.get(f"{path}/{id_}", headers=other.headers).status_code
                probes += 1
                if status != 404:
                    leaks.append(f"{other.name} got {status} for {owner.name}'s {key}")
            for path in PATHS.values():
                listed = client.get(path, headers=other.headers).json()
                probes += 1
                for row in listed:
                    id_ = uuid.UUID(row["id"])
                    if id_ in owned:
                        leaks.append(f"{other.name} sees {owned[id_]} in GET {path}")
    return leaks, probes
