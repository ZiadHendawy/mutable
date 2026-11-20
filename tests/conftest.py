"""Shared test setup.

Tests call the real app in-process (TestClient) against the real Postgres, so the real
constraints and Row-Level Security are what get tested -- no SQLite, and no mocks except
the embedder.

The embedder is the one stand-in. The app gets its embedder from `get_embedder`, and this
file swaps that for `FakeEmbedder` (through `app.dependency_overrides`), so every record a
test creates is embedded by the fake: instantly, without loading the real model, and with a
vector the test can work out for itself. `test_embeddings.py` tests the real model directly.

Every test that needs a tenant asks for the `tenant` fixture (and `other_tenant` when it
needs two). Each is a brand-new tenant, so a test only ever sees the rows it wrote itself:
nothing is shared between tests, or left over from earlier runs against the same database.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.embeddings import FakeEmbedder, get_embedder
from app.main import app

# Set when pytest loads this file, before any test runs, so it also covers the TestClient
# that test_transactions.py creates for itself.
app.dependency_overrides[get_embedder] = FakeEmbedder


class TenantClient:
    """The app as seen by one tenant: every request carries that tenant's X-Tenant-Id."""

    def __init__(self, client: TestClient) -> None:
        self.id = str(uuid.uuid4())
        self.headers = {"X-Tenant-Id": self.id}
        self._client = client

    def get(self, path: str) -> Response:
        return self._client.get(path, headers=self.headers)

    def post(self, path: str, json: dict) -> Response:
        return self._client.post(path, json=json, headers=self.headers)

    def delete(self, path: str) -> Response:
        return self._client.delete(path, headers=self.headers)


@pytest.fixture(scope="session")
def client() -> TestClient:
    """The app with no tenant attached -- for requests that send no header, or their own."""
    return TestClient(app)


@pytest.fixture
def tenant(client: TestClient) -> TenantClient:
    return TenantClient(client)


@pytest.fixture
def other_tenant(client: TestClient) -> TenantClient:
    return TenantClient(client)
