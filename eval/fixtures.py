"""Eval fixture format: typed records and gold questions, keyed by stable names.

Layout -- one directory per persona under eval/data/:

    records.yaml    facts / preferences / episodes to seed through the API
    questions.yaml  gold questions (optional -- the isolation-only tenant has none)

Records are referenced by a stable ``key`` (``<persona>.<type>.<slug>``, e.g.
``maya.pref.diet.v2``), never by UUID: UUIDs are assigned by the API at seed time
and the loader maps keys to them. Personas carry no tenant id either -- each seed
run registers a fresh tenant, so re-runs never accumulate duplicate rows.

Dates may be written as plain ``2025-05-01`` (read as midnight UTC) or full ISO
timestamps.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

DATA_DIR = Path(__file__).parent / "data"

RecordType = Literal["fact", "preference", "episode"]
TYPE_SEGMENT: dict[str, RecordType] = {"fact": "fact", "pref": "preference", "ep": "episode"}


def _date_to_datetime(value: object) -> object:
    # YAML turns 2025-05-01 into a date; pydantic won't widen that to a datetime.
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    return value


def _assume_utc(value: datetime) -> datetime:
    # Naive values (bare dates, or strings without an offset) are UTC, so every
    # fixture timestamp compares cleanly against every other.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


UtcDatetime = Annotated[datetime, BeforeValidator(_date_to_datetime), AfterValidator(_assume_utc)]
Key = Annotated[str, Field(pattern=r"^[a-z]+\.(fact|pref|ep)\.[a-z0-9_]+(\.v\d+)?$")]


class _Strict(BaseModel):
    # Typos in hand-written YAML should fail loudly, not silently drop a field.
    model_config = ConfigDict(extra="forbid")


class _Record(_Strict):
    key: Key
    content: str
    confidence: float = Field(ge=0, le=1)
    source: str | None = None
    valid_from: UtcDatetime | None = None


class FactFixture(_Record):
    pass


class PreferenceFixture(_Record):
    strength: float = Field(ge=-1, le=1)
    supersedes: Key | None = None


class EpisodeFixture(_Record):
    event_time: UtcDatetime
    event_time_end: UtcDatetime | None = None


class PersonaRecords(_Strict):
    persona: str
    facts: list[FactFixture] = []
    preferences: list[PreferenceFixture] = []
    episodes: list[EpisodeFixture] = []

    def all_records(self) -> list[_Record]:
        return [*self.facts, *self.preferences, *self.episodes]

    def record_type(self, key: str) -> RecordType:
        return TYPE_SEGMENT[key.split(".")[1]]

    def successor_of(self) -> dict[str, str]:
        """Superseded key -> the key that replaced it."""
        return {p.supersedes: p.key for p in self.preferences if p.supersedes}

    @model_validator(mode="after")
    def check_records(self) -> Self:
        seen: set[str] = set()
        for record, expected in (
            *((f, "fact") for f in self.facts),
            *((p, "preference") for p in self.preferences),
            *((e, "episode") for e in self.episodes),
        ):
            if record.key in seen:
                raise ValueError(f"duplicate key {record.key}")
            seen.add(record.key)
            if self.record_type(record.key) != expected:
                raise ValueError(f"{record.key} is listed under {expected}s but keyed otherwise")

        # Supersede chains: must point backwards in file order (the loader seeds
        # top to bottom, so the old record has to exist first), each record is
        # replaced at most once, and both ends carry explicit dates so the
        # validity windows are real history, not seed-run timestamps.
        earlier: dict[str, PreferenceFixture] = {}
        for pref in self.preferences:
            if pref.supersedes is not None:
                old = earlier.get(pref.supersedes)
                if old is None:
                    raise ValueError(
                        f"{pref.key} supersedes {pref.supersedes}, which is not an earlier "
                        "preference in this file"
                    )
                if old.valid_from is None or pref.valid_from is None:
                    raise ValueError(f"{old.key} -> {pref.key}: both need valid_from")
                if pref.valid_from < old.valid_from:
                    raise ValueError(f"{pref.key} is dated before {old.key}, which it replaces")
            earlier[pref.key] = pref
        replaced = [p.supersedes for p in self.preferences if p.supersedes]
        if len(replaced) != len(set(replaced)):
            raise ValueError("a preference is superseded more than once")

        for ep in self.episodes:
            if ep.event_time_end is not None and ep.event_time_end < ep.event_time:
                raise ValueError(f"{ep.key}: event_time_end before event_time")
        return self


QuestionCategory = Literal[
    "fact",
    "preference",  # a stable preference, no supersede chain involved
    "preference_current",  # current end of a chain; superseded versions must not surface
    "preference_historical",  # an earlier link of a chain must still be retrievable
    "episode",
    "cross_type",  # answer needs records of more than one type
]


class GoldQuestion(_Strict):
    id: str = Field(pattern=r"^q\d{3}$")
    question: str
    category: QuestionCategory
    gold: list[Key] = Field(min_length=1)
    # Keys that must NOT appear in the top-k -- e.g. the superseded version for a
    # current-preference question. A hit here fails the question even if gold was found.
    must_exclude: list[Key] = []
    # Point in time the question is asking about ("in 2023, ..."), if any.
    as_of: UtcDatetime | None = None

    @model_validator(mode="after")
    def check_disjoint(self) -> Self:
        if set(self.gold) & set(self.must_exclude):
            raise ValueError(f"{self.id}: a key is in both gold and must_exclude")
        return self


class Persona(_Strict):
    records: PersonaRecords
    questions: list[GoldQuestion] = []

    def expected_route(self, question: GoldQuestion) -> set[RecordType]:
        """The types a correct router must send this question to -- derived from its
        gold records rather than labeled separately, so the two can't disagree."""
        return {self.records.record_type(key) for key in question.gold}

    @model_validator(mode="after")
    def check_questions(self) -> Self:
        records = {r.key: r for r in self.records.all_records()}
        successor = self.records.successor_of()
        predecessor = {new: old for old, new in successor.items()}

        def chain_before(key: str) -> list[str]:
            out = []
            while key in predecessor:
                key = predecessor[key]
                out.append(key)
            return out

        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate question id")

        for q in self.questions:
            for key in (*q.gold, *q.must_exclude):
                if key not in records:
                    raise ValueError(f"{q.id}: unknown record key {key}")
            if len(self.expected_route(q)) > 1 and q.category != "cross_type":
                raise ValueError(f"{q.id}: gold spans several types; category must be cross_type")

            gold_prefs = [k for k in q.gold if self.records.record_type(k) == "preference"]
            if q.category == "preference_current":
                for key in gold_prefs:
                    if key in successor:
                        raise ValueError(f"{q.id}: {key} is superseded, not current")
                    missing = set(chain_before(key)) - set(q.must_exclude)
                    if missing:
                        raise ValueError(f"{q.id}: must_exclude is missing {sorted(missing)}")
            if q.category == "preference_historical":
                if not any(k in successor for k in gold_prefs):
                    raise ValueError(f"{q.id}: historical question with no superseded gold")
                if q.as_of is not None:
                    for key in gold_prefs:
                        if not _valid_at(records[key], successor, records, q.as_of):
                            raise ValueError(f"{q.id}: {key} was not valid at {q.as_of}")
        return self


def _valid_at(
    record: _Record, successor: dict[str, str], records: dict[str, _Record], when: datetime
) -> bool:
    if record.valid_from is not None and when < record.valid_from:
        return False
    nxt = successor.get(record.key)
    return nxt is None or when < records[nxt].valid_from


def load_persona(name: str, data_dir: Path = DATA_DIR) -> Persona:
    directory = data_dir / name
    records = yaml.safe_load((directory / "records.yaml").read_text())
    questions_path = directory / "questions.yaml"
    questions = yaml.safe_load(questions_path.read_text()) if questions_path.exists() else []
    return Persona.model_validate({"records": records, "questions": questions or []})
