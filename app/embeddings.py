"""Turning text into vectors, so search can compare meanings rather than exact words.

An embedder turns each text into a vector: a fixed-length list of numbers. Texts that mean
similar things get vectors that are close together, and vector search ranks by that closeness.

Two embedders share one interface, `Embedder`:

- `LocalEmbedder`, the real one: a small model that runs on this machine. No API key, and no
  network once the model is downloaded.
- `FakeEmbedder`, for tests: instant and predictable. Texts that share words get closer vectors.

The app gets its embedder from the `get_embedder` dependency, so tests can swap in the fake
through `app.dependency_overrides`.
"""

import math
import re
import zlib
from functools import cache
from typing import Protocol

from fastembed import TextEmbedding

# Every vector has DIMENSION numbers, and the database column is sized to match, so
# changing the model means a migration and embedding every record again.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSION = 384


class Embedder(Protocol):
    """Turns texts into vectors of `dimension` numbers each, one vector per text."""

    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedder:
    """The real embedder: MODEL_NAME, run on the CPU by the fastembed library."""

    dimension = DIMENSION

    def __init__(self) -> None:
        # Loading the model takes a moment, so the app creates one and shares it
        # (get_embedder). fastembed downloads it on first use into the folder named by
        # FASTEMBED_CACHE_PATH; the Docker image and CI download it in advance.
        self._model = TextEmbedding(MODEL_NAME)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # fastembed returns numpy arrays; the rest of the app uses plain lists.
        return [vector.tolist() for vector in self._model.embed(texts)]


class FakeEmbedder:
    """A stand-in for tests: each word adds 1 to one of the vector's numbers.

    A word always lands on the same position, so the same text always gets the same
    vector, and texts that share words get closer vectors. It knows nothing about meaning:
    to the fake, "tea" is as far from "coffee" as it is from "Lisbon".
    """

    dimension = DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            # A checksum of the word picks its position. Not hash(): Python's hash() of a
            # string changes from run to run, which would make test results change too.
            vector[zlib.crc32(word.encode()) % self.dimension] += 1.0
        # Scale to length 1, like the real model's vectors.
        length = math.hypot(*vector)
        if length == 0:  # a text with no words
            return vector
        return [number / length for number in vector]


@cache
def get_embedder() -> Embedder:
    """The FastAPI dependency: one LocalEmbedder, created on first use and shared after.

    Created lazily, not at startup, so tests that swap in the fake never load the model.
    """
    return LocalEmbedder()
