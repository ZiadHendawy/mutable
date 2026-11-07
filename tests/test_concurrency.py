"""Concurrent writes to the same row.

Two requests that both supersede the same preference, sent at the same moment. Each runs
on its own thread, so each gets its own Session and its own pooled connection -- the same
as two real clients hitting the API at once.

Releasing two threads together isn't enough to make them interleave: the window between
reading the old row and writing it is a few milliseconds, so one request usually finishes
before the other starts. `pause_after_reading` makes it deterministic by holding each
request right after it reads, until both have read.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial

import pytest
from httpx import Response
from sqlalchemy.orm import Session

# How long a request waits at the pause for the other one to catch up. If the other
# request is blocked on a row lock it will never arrive, so the wait times out and the
# first request carries on. A fixed endpoint therefore makes this test ~1 s slower.
PAUSE_TIMEOUT_SECONDS = 1.0


@contextmanager
def pause_after_reading(monkeypatch: pytest.MonkeyPatch, parties: int) -> Iterator[None]:
    """Make every Session.get wait until `parties` requests have each done one."""
    barrier = threading.Barrier(parties, timeout=PAUSE_TIMEOUT_SECONDS)
    real_get = Session.get

    def get_then_wait(self: Session, *args: object, **kwargs: object) -> object:
        result = real_get(self, *args, **kwargs)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # timed out: the other request is blocked, so stop waiting for it
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Session, "get", get_then_wait)
        yield


def run_concurrently(calls: list[Callable[[], Response]]) -> list[Response]:
    """Start every call at the same moment, each on its own thread; return results in order."""
    start = threading.Barrier(len(calls))
    results: list[Response | BaseException | None] = [None] * len(calls)

    def worker(index: int, call: Callable[[], Response]) -> None:
        start.wait()
        try:
            results[index] = call()
        except BaseException as exc:  # re-raised below, on the test's own thread
            results[index] = exc

    threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads), "a request never finished"

    for result in results:
        if isinstance(result, BaseException):
            raise result
    return results  # type: ignore[return-value]


def test_concurrent_supersede_has_exactly_one_winner(tenant, monkeypatch) -> None:
    old = tenant.post(
        "/preferences", json={"content": "prefers tea", "confidence": 0.8, "strength": 0.6}
    ).json()

    calls = [
        partial(
            tenant.post,
            "/preferences",
            json={
                "content": f"replacement {i}",
                "confidence": 0.8,
                "strength": 0.6,
                "supersedes": old["id"],
            },
        )
        for i in range(2)
    ]
    with pause_after_reading(monkeypatch, parties=2):
        responses = run_concurrently(calls)

    # The API's answer: one request won, the other was told it lost.
    assert sorted(r.status_code for r in responses) == [201, 409]
    winner = next(r.json() for r in responses if r.status_code == 201)

    # Exactly one current version, and it's the winner -- catches a loser whose row was
    # committed anyway, which the status codes alone can't see.
    current = tenant.get("/preferences").json()
    assert [p["id"] for p in current] == [winner["id"]]

    # The old row was closed by the winner, with no gap or overlap -- catches the lost
    # update, where the second UPDATE overwrites the first one's link.
    old_after = tenant.get(f"/preferences/{old['id']}").json()
    assert old_after["superseded_by"] == winner["id"]
    assert old_after["valid_to"] == winner["valid_from"]
