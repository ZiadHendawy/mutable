"""Reading a question to decide what to search: the plan behind /search.

The plan says which point in time the question is about:

- "now", the default: current versions only ("What's Maya's diet these days?")
- "as_of" a date: the versions that were true then ("Was Maya vegetarian back in 2023?")
- "history": every version, current or not ("How has Maya's diet changed over time?")

It's made by rules, not a model: a handful of patterns, checked in order, so every decision
is predictable and can be explained. Rules can't turn a phrase like "when she was at
university" into a date, so those fall back to "history" (docs/design.md, gap 4.9).
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

TimeScope = Literal["now", "as_of", "history"]


@dataclass(frozen=True)
class SearchPlan:
    time: TimeScope = "now"
    as_of: datetime | None = None  # set exactly when time is "as_of"


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

YEAR = r"(?P<year>(?:19|20)\d{2})"
MONTH = r"(?P<month>" + "|".join(MONTHS) + r")"
PART = r"(?P<part>early|mid|late)"

# "in March 2025", "in early 2025", "back in 2023", "during 2020", "2022". The year must
# stand alone, so "1995s" or "20221" don't match.
DATE_PHRASE = re.compile(rf"\b(?:(?:{MONTH}|{PART})[\s-]+(?:of\s+)?)?{YEAR}\b", re.IGNORECASE)
YEARS_AGO = re.compile(r"\b(?P<n>\d+|a|one|two|three|four|five)\s+years?\s+ago\b", re.IGNORECASE)
LAST_YEAR = re.compile(r"\blast\s+year\b", re.IGNORECASE)
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


def plan_search(question: str, today: date | None = None) -> SearchPlan:
    """The plan for a question. `today` anchors relative dates ("last year")."""
    today = today or datetime.now(UTC).date()

    as_of = _date_in(question, today)
    if as_of is not None:
        return SearchPlan(time="as_of", as_of=as_of)
    if HISTORY.search(question):
        return SearchPlan(time="history")
    return SearchPlan()


def _date_in(question: str, today: date) -> datetime | None:
    """The point in time a question names, if it names one."""
    if match := DATE_PHRASE.search(question):
        year = int(match["year"])
        if match["month"]:
            # A month means its middle.
            return _utc(year, MONTHS[match["month"].lower()], 15)
        if match["part"]:
            return _utc(year, PART_OF_YEAR[match["part"].lower()], 1)
        return _utc(year, MID_YEAR, 1)
    if match := YEARS_AGO.search(question):
        n = match["n"].lower()
        years = NUMBER_WORDS[n] if n in NUMBER_WORDS else int(n)
        return _utc(today.year - years, MID_YEAR, 1)
    if LAST_YEAR.search(question):
        return _utc(today.year - 1, MID_YEAR, 1)
    return None


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)
