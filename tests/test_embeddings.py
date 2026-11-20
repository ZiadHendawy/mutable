"""The embedders: the fake is predictable, and the real model puts related texts closer.

The LocalEmbedder tests run the real model. The Docker image and CI download it in advance;
anywhere else, the first run downloads it.
"""

import math

import pytest

from app.embeddings import FakeEmbedder, LocalEmbedder, get_embedder

TEA = "prefers tea over coffee"
GREEN_TEA = "likes green tea"
LISBON = "lives in Lisbon"


def length(vector: list[float]) -> float:
    return math.sqrt(sum(number * number for number in vector))


def test_fake_embedder_gives_the_same_vector_every_time() -> None:
    first = FakeEmbedder().embed([TEA])
    second = FakeEmbedder().embed([TEA])
    assert first == second
    # And in every run: "tea" always lands on the same position. (Python's built-in hash()
    # would move it from run to run, and this check would fail.)
    [tea] = FakeEmbedder().embed(["tea"])
    assert tea.index(1.0) == 306


def test_fake_embedder_gives_384_numbers_scaled_to_length_1() -> None:
    vectors = FakeEmbedder().embed([TEA, LISBON])
    assert FakeEmbedder().dimension == 384
    assert [len(vector) for vector in vectors] == [384, 384]
    for vector in vectors:
        assert math.isclose(length(vector), 1.0)


def test_fake_embedder_puts_texts_that_share_words_closer() -> None:
    tea, green_tea, lisbon = FakeEmbedder().embed([TEA, GREEN_TEA, LISBON])
    assert math.dist(tea, green_tea) < math.dist(tea, lisbon)


def test_get_embedder_shares_one_local_embedder() -> None:
    assert isinstance(get_embedder(), LocalEmbedder)
    assert get_embedder() is get_embedder()


@pytest.fixture(scope="module")
def local_embedder() -> LocalEmbedder:
    # The app's shared instance, so the model loads only once for these tests.
    embedder = get_embedder()
    assert isinstance(embedder, LocalEmbedder)
    return embedder


def test_local_embedder_gives_384_numbers_scaled_to_length_1(
    local_embedder: LocalEmbedder,
) -> None:
    vectors = local_embedder.embed([TEA, LISBON])
    assert local_embedder.dimension == 384
    assert [len(vector) for vector in vectors] == [384, 384]
    for vector in vectors:
        # The model computes in 32-bit numbers, so allow for rounding in the last digits.
        assert math.isclose(length(vector), 1.0, rel_tol=1e-6)


def test_local_embedder_returns_vectors_in_the_order_of_the_texts(
    local_embedder: LocalEmbedder,
) -> None:
    # Each text embedded on its own can't come back in the wrong order, so it's the reference.
    [tea] = local_embedder.embed([TEA])
    [lisbon] = local_embedder.embed([LISBON])
    together = local_embedder.embed([TEA, LISBON])
    assert together[0] == pytest.approx(tea, abs=1e-5)
    assert together[1] == pytest.approx(lisbon, abs=1e-5)


def test_local_embedder_puts_related_texts_closer(local_embedder: LocalEmbedder) -> None:
    tea, green_tea, lisbon = local_embedder.embed([TEA, GREEN_TEA, LISBON])
    assert math.dist(tea, green_tea) < math.dist(tea, lisbon)
