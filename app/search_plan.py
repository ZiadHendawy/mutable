"""Reading a question to decide what to search: the plan behind /search.

The plan says which kinds of record to search:

- episodes for questions about events ("When did Maya move to Lisbon?")
- preferences for questions about likes and habits ("Does Maya like spicy food?")
- both for "why" questions, which link a change to the event behind it
- all three otherwise. Facts are too varied to spot reliably, so they're never searched
  alone: a question that matches no rule searches everything

which point in time the question is about:

- "now", the default: current versions only ("What's Maya's diet these days?")
- "as_of" a date: the versions that were true then ("Was Maya vegetarian back in 2023?")
- "history": every version, current or not ("How has Maya's diet changed over time?")

and, for episodes, which period they must fall in ("in October 2025"), and whether the
question wants the most recent one ("When did she last visit Toronto?").

It's made by rules, not a model: a handful of patterns, checked in order, so every decision
is predictable and can be explained. Rules can't turn a phrase like "when she was at
university" into a date, so those fall back to "history" (docs/design.md, gap 4.9).
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

TimeScope = Literal["now", "as_of", "history"]
RecordType = Literal["fact", "preference", "episode"]

ALL_TYPES: frozenset[RecordType] = frozenset({"fact", "preference", "episode"})


@dataclass(frozen=True)
class Period:
    """A stretch of time a question names: "October 2025" is October 1 to November 1."""

    start: datetime  # inclusive
    end: datetime  # exclusive


@dataclass(frozen=True)
class SearchPlan:
    types: frozenset[RecordType] = ALL_TYPES
    time: TimeScope = "now"
    as_of: datetime | None = None  # set exactly when time is "as_of"
    # The period the question names, if any. Episodes must overlap it.
    period: Period | None = None
    # The question asks for the most recent event ("When did she last visit Toronto?").
    latest: bool = False


MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}

# A year on its own means its middle, so a version that changed during the year is decided
# by what was true halfway through. "Early" and "late" move that to March and November.
PART_OF_YEAR = {"early": 3, "mid": 7, "late": 11}
MID_YEAR = 7
# The months each part of a year covers, as (first month, first month after): thirds.
PART_MONTHS = {"early": (1, 5), "mid": (5, 9), "late": (9, 13)}

YEAR = r"(?P<year>(?:19|20)\d{2})"
MONTH = r"(?P<month>" + "|".join(MONTHS) + r")"
PART = r"(?P<part>early|mid|late)"

# "in March 2025", "in early 2025", "back in 2023", "during 2020", "2022". The year must
# stand alone, so "1995s" or "20221" don't match.
DATE_PHRASE = re.compile(rf"\b(?:(?:{MONTH}|{PART})[\s-]+(?:of\s+)?)?{YEAR}\b", re.IGNORECASE)
YEARS_AGO = re.compile(r"\b(?P<n>\d+|a|one|two|three|four|five)\s+years?\s+ago\b", re.IGNORECASE)
LAST_YEAR = re.compile(r"\blast\s+year\b", re.IGNORECASE)
# "last visit", "the most recent trip", "latest", "recently". Not "last year" (a date) or
# "last week" and the like.
LATEST = re.compile(
    r"\b(?:most\s+recent(?:ly)?|latest|recently|last(?!\s+(?:year|month|week|day|night|time)\b))\b",
    re.IGNORECASE,
)
NUMBER_WORDS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Phrases that ask about the past without a date. Each is a whole-word match.
HISTORY_PHRASES = [
    r"used\s+to",
    # "did she use to", but not "what does she use to edit photos"
    r"did\s+\w+\s+use\s+to",
    r"before",
    r"previously",
    r"originally",
    r"at\s+first",
    r"in\s+the\s+past",
    r"back\s+then",
    r"over\s+time",
    r"over\s+the\s+years",
    r"change[ds]?",
    r"changing",
    r"history",
    r"early\s+in\s+(?:her|his|their|my)\s+career",
    r"when\s+(?:she|he|they|i)\s+(?:was|were)",
]
HISTORY = re.compile(r"\b(?:" + "|".join(HISTORY_PHRASES) + r")\b", re.IGNORECASE)


def _phrases(*patterns: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)


# A name or pronoun between two words: "what did Maya do", "how did she do".
WHO = r"\w+(?:'s)?"

WHY = _phrases(r"why")
# Questions about something that happened, in the past tense. "When did" is an event;
# "when does she like to" is a habit, so only the past tense counts. A question word only
# decides the type when it starts the question: in "What's her role, and when did she
# start?", the first half is about a fact.
EPISODE_OPENINGS = re.compile(
    r"^\s*(?:"
    + "|".join(
        [
            r"when\s+did",
            rf"what\s+did\s+{WHO}\s+do",
            rf"how\s+did\s+{WHO}\s+do",
            rf"where\s+did\s+{WHO}\s+travel",
            r"what\s+happened",
            rf"what\s+(?:trips?|talks?|visits?|events?)\s+(?:has|have|did)\s+{WHO}",
        ]
    )
    + r")\b",
    re.IGNORECASE,
)
EPISODE_ANYWHERE = _phrases(r"last\s+visit(?:ed)?")


# Questions about likes, dislikes and habits.
PREFERENCE_CUES = _phrases(
    r"prefers?",
    r"preferred",
    r"likes?",
    r"enjoys?",
    r"rather",
    r"favou?rite",
    r"feel\s+about",
    r"want\s+to",
    r"diet",
    r"habits?",
)


def plan_search(question: str, today: date | None = None) -> SearchPlan:
    """The plan for a question. `today` anchors relative dates ("last year")."""
    today = today or datetime.now(UTC).date()
    types = _types_for(question)

    latest = bool(LATEST.search(question))

    named = _date_in(question, today)
    if named is not None:
        point, period = named
        return SearchPlan(types=types, time="as_of", as_of=point, period=period, latest=latest)
    if HISTORY.search(question):
        return SearchPlan(types=types, time="history", latest=latest)
    return SearchPlan(types=types, latest=latest)


def _types_for(question: str) -> frozenset[RecordType]:
    """Which kinds of record a question is about. All three when unsure."""
    if WHY.search(question):
        return frozenset({"episode", "preference"})
    episode = bool(EPISODE_OPENINGS.match(question) or EPISODE_ANYWHERE.search(question))
    preference = bool(PREFERENCE_CUES.search(question))
    if episode and not preference:
        return frozenset({"episode"})
    if preference and not episode:
        return frozenset({"preference"})
    return ALL_TYPES


def _date_in(question: str, today: date) -> tuple[datetime, Period] | None:
    """The point in time a question names, and the period around it, if it names one."""
    if match := DATE_PHRASE.search(question):
        year = int(match["year"])
        if match["month"]:
            # A month means its middle.
            month = MONTHS[match["month"].lower()]
            return _utc(year, month, 15), _months(year, month, month + 1)
        if match["part"]:
            part = match["part"].lower()
            return _utc(year, PART_OF_YEAR[part], 1), _months(year, *PART_MONTHS[part])
        return _utc(year, MID_YEAR, 1), _months(year, 1, 13)
    if match := YEARS_AGO.search(question):
        n = match["n"].lower()
        year = today.year - (NUMBER_WORDS[n] if n in NUMBER_WORDS else int(n))
        return _utc(year, MID_YEAR, 1), _months(year, 1, 13)
    if LAST_YEAR.search(question):
        year = today.year - 1
        return _utc(year, MID_YEAR, 1), _months(year, 1, 13)
    return None


def _months(year: int, first: int, after: int) -> Period:
    """From the first day of month `first` to the first day of month `after` (13 is next
    January)."""
    end = _utc(year + 1, 1, 1) if after == 13 else _utc(year, after, 1)
    return Period(start=_utc(year, first, 1), end=end)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)
