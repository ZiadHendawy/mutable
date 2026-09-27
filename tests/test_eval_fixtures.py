import copy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from eval.fixtures import Persona, load_persona

BASE = {
    "records": {
        "persona": "Test",
        "facts": [{"key": "t.fact.city", "content": "lives in Lisbon", "confidence": 0.9}],
        "preferences": [
            {
                "key": "t.pref.diet.v1",
                "content": "vegetarian",
                "confidence": 0.9,
                "strength": 0.9,
                "valid_from": "2016-01-01",
            },
            {
                "key": "t.pref.diet.v2",
                "content": "pescatarian",
                "confidence": 0.9,
                "strength": 0.8,
                "valid_from": "2025-05-01",
                "supersedes": "t.pref.diet.v1",
            },
        ],
        "episodes": [
            {
                "key": "t.ep.trip",
                "content": "trip to Morocco",
                "confidence": 0.9,
                "event_time": "2025-10-04",
            }
        ],
    },
    "questions": [
        {
            "id": "q001",
            "question": "current diet?",
            "category": "preference_current",
            "gold": ["t.pref.diet.v2"],
            "must_exclude": ["t.pref.diet.v1"],
        },
        {
            "id": "q002",
            "question": "diet in 2023?",
            "category": "preference_historical",
            "gold": ["t.pref.diet.v1"],
            "as_of": "2023-06-01",
        },
    ],
}


def _persona(mutate=None) -> Persona:
    data = copy.deepcopy(BASE)
    if mutate:
        mutate(data)
    return Persona.model_validate(data)


@pytest.mark.parametrize("name", ["maya", "jonas"])
def test_shipped_fixtures_validate(name: str) -> None:
    persona = load_persona(name)
    assert persona.records.all_records()


def test_isolation_persona_has_no_questions() -> None:
    assert load_persona("jonas").questions == []


def test_valid_base_and_date_normalization() -> None:
    persona = _persona()
    assert persona.records.preferences[0].valid_from == datetime(2016, 1, 1, tzinfo=UTC)
    assert persona.expected_route(persona.questions[0]) == {"preference"}


def _set(path, value):
    def mutate(data):
        target = data
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [
        # unknown field (typo) in hand-written YAML
        _set(["records", "facts", 0, "confidance"], 0.9),
        # duplicate key
        _set(["records", "preferences", 1, "key"], "t.pref.diet.v1"),
        # key's type segment disagrees with the list it's under
        _set(["records", "facts", 0, "key"], "t.pref.city"),
        # supersedes a key that doesn't exist earlier in the file
        _set(["records", "preferences", 1, "supersedes"], "t.pref.nope"),
        # replacement dated before the record it replaces
        _set(["records", "preferences", 1, "valid_from"], "2010-01-01"),
        # chain without explicit dates
        _set(["records", "preferences", 0, "valid_from"], None),
        # gold references an unknown key
        _set(["questions", 0, "gold"], ["t.fact.nope"]),
        # current-preference question pointing at a superseded record
        _set(["questions", 0, "gold"], ["t.pref.diet.v1"]),
        # current-preference question that forgets to exclude the old version
        _set(["questions", 0, "must_exclude"], []),
        # historical question with no superseded gold
        _set(["questions", 1, "gold"], ["t.pref.diet.v2"]),
        # as_of outside the gold record's validity window
        _set(["questions", 1, "as_of"], "2025-06-01"),
        # gold spanning types without the cross_type category
        _set(["questions", 0, "gold"], ["t.pref.diet.v2", "t.fact.city"]),
        # same key in gold and must_exclude
        _set(["questions", 0, "must_exclude"], ["t.pref.diet.v1", "t.pref.diet.v2"]),
        # duplicate question id
        _set(["questions", 1, "id"], "q001"),
    ],
)
def test_invalid_fixtures_rejected(mutate) -> None:
    with pytest.raises(ValidationError):
        _persona(mutate)


def test_preference_superseded_twice_rejected() -> None:
    def mutate(data):
        data["records"]["preferences"].append(
            {
                "key": "t.pref.diet.v3",
                "content": "vegan",
                "confidence": 0.9,
                "strength": 0.9,
                "valid_from": "2026-01-01",
                "supersedes": "t.pref.diet.v1",
            }
        )

    with pytest.raises(ValidationError):
        _persona(mutate)
