import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app

# raise_server_exceptions=False: see the status code a real client would get,
# instead of the test re-raising the server-side exception.
client = TestClient(app, raise_server_exceptions=False)


def test_failed_commit_is_not_reported_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_commit(self: Session) -> None:
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(Session, "commit", failing_commit)
    tenant = {"X-Tenant-Id": str(uuid.uuid4())}

    response = client.post("/facts", json={"content": "x", "confidence": 0.5}, headers=tenant)

    # Before the fix this was 201: the commit ran after the response was sent.
    assert response.status_code == 500

    monkeypatch.undo()
    assert client.get("/facts", headers=tenant).json() == []
