"""Shared test setup.

Tests call the real app in-process (TestClient) against the real Postgres, so the real
constraints and Row-Level Security are what get tested -- no mocks, no SQLite.

Every test that needs a tenant asks for the `tenant` fixture (and `other_tenant` when it
needs two). Each is a brand-new tenant, so a test only ever sees the rows it wrote itself:
nothing is shared between tests, or left over from earlier runs against the same database.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app


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
