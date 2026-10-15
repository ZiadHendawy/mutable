"""Creating a record stores what search needs: its vector and its words.

The API's responses leave both columns out on purpose (384 numbers would bury the useful
fields), so these tests read them straight from Postgres, as the API's own restricted user
with the tenant set, like test_isolation.py does.
"""

import pytest
from sqlalchemy import select, text

from app.db import SessionLocal
from app.embeddings import FakeEmbedder
from app.models import MemoryEpisode, MemoryFact, MemoryPreference

CONTENT = "Lives in Lisbon"

# Each memory type: where it's created, its table, and the other fields it needs.
MEMORY_TYPES = [
    pytest.param("/facts", MemoryFact, {"confidence": 0.9}, id="fact"),
    pytest.param(
        "/preferences", MemoryPreference, {"confidence": 0.8, "strength": 0.5}, id="preference"
    ),
    pytest.param(
        "/episodes",
        MemoryEpisode,
        {"confidence": 0.7, "event_time": "2026-03-04T14:00:00Z"},
        id="episode",
    ),
]


def read_search_columns(
    model: type[MemoryFact | MemoryPreference | MemoryEpisode], record_id: str, tenant_id: str
) -> tuple[list[float] | None, str]:
    """A stored record's embedding and content_words, read as the API's user would."""
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        query = select(model.embedding, model.content_words).where(model.id == record_id)
        embedding, content_words = db.execute(query).one()
        return embedding, content_words


@pytest.mark.parametrize(("path", "model", "fields"), MEMORY_TYPES)
def test_creating_a_record_stores_its_vector(tenant, path, model, fields) -> None:
    response = tenant.post(path, json={"content": CONTENT, **fields})
    assert response.status_code == 201

    embedding, _ = read_search_columns(model, response.json()["id"], tenant.id)
    # The fake embedder's vector for this content (tests/conftest.py swaps it in). Postgres
    # keeps each number in 32 bits, so it matches up to rounding.
    [expected] = FakeEmbedder().embed([CONTENT])
    assert len(embedding) == 384
    assert embedding == pytest.approx(expected)


@pytest.mark.parametrize(("path", "model", "fields"), MEMORY_TYPES)
def test_creating_a_record_stores_its_words(tenant, path, model, fields) -> None:
    response = tenant.post(path, json={"content": CONTENT, **fields})
    assert response.status_code == 201

    _, content_words = read_search_columns(model, response.json()["id"], tenant.id)
    # Each word in its base form ("lives" -> "live"), with its position in the content.
    # "in" is too common to be worth searching for, so it's left out.
    assert content_words == "'lisbon':3 'live':1"


@pytest.mark.parametrize(("path", "model", "fields"), MEMORY_TYPES)
def test_responses_leave_out_the_search_columns(tenant, path, model, fields) -> None:
    created = tenant.post(path, json={"content": CONTENT, **fields}).json()
    fetched = tenant.get(f"{path}/{created['id']}").json()
    for body in (created, fetched):
        assert "embedding" not in body
        assert "content_words" not in body


@pytest.mark.parametrize(("path", "model", "fields"), MEMORY_TYPES)
def test_empty_content_is_rejected(tenant, path, model, fields) -> None:
    # An empty text has no meaning to turn into a vector, and no words to find.
    response = tenant.post(path, json={"content": "", **fields})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "content"]
