"""plan_search: the rules that read a question's time scope and record types.

Pure functions, no database.
"""

from datetime import UTC, date, datetime

import pytest

from app.search_plan import Period, SearchPlan, plan_search

TODAY = date(2026, 11, 20)


def as_of(year: int, month: int, day: int) -> SearchPlan:
    return SearchPlan(time="as_of", as_of=datetime(year, month, day, tzinfo=UTC))


def time_of(plan: SearchPlan) -> tuple:
    return plan.time, plan.as_of


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # A year means its middle; "early", "mid" and "late" move it; a month means its middle.
        ("Was she vegetarian back in 2023?", as_of(2023, 7, 1)),
        ("What exercise was she doing in early 2025?", as_of(2025, 3, 1)),
        ("Where was she living in mid-2024?", as_of(2024, 7, 1)),
        ("What did she drink in late 2019?", as_of(2019, 11, 1)),
        ("Where did she travel in October 2025?", as_of(2025, 10, 15)),
        ("What happened in March of 2025?", as_of(2025, 3, 15)),
        # Relative to today.
        ("What was she reading last year?", as_of(2025, 7, 1)),
        ("Where did she work 3 years ago?", as_of(2023, 7, 1)),
        ("Where did she work two years ago?", as_of(2024, 7, 1)),
        # The past, with no date.
        ("How did she use to plan her trips?", SearchPlan(time="history")),
        ("What did she used to drink?", SearchPlan(time="history")),
        ("What did she use before Figma?", SearchPlan(time="history")),
        ("How has her diet changed over time?", SearchPlan(time="history")),
        ("What company did she want to join early in her career?", SearchPlan(time="history")),
        ("What was her habit when she was at university?", SearchPlan(time="history")),
        ("Did she previously live in Toronto?", SearchPlan(time="history")),
        # Everything else is about now.
        ("What's her diet these days?", SearchPlan()),
        ("Does she still read paper books?", SearchPlan()),
        ("When did she last visit Toronto?", SearchPlan()),
        ("Why did she switch to Figma?", SearchPlan()),
    ],
)
def test_reads_the_time_scope(question: str, expected: SearchPlan) -> None:
    assert time_of(plan_search(question, TODAY)) == time_of(expected)


def test_a_date_wins_over_a_history_phrase() -> None:
    assert time_of(plan_search("What did she use before 2020?", TODAY)) == time_of(
        as_of(2020, 7, 1)
    )


@pytest.mark.parametrize(
    "question",
    [
        "How many cups does she have, 20221 or more?",  # not a year: too many digits
        "Does she like the 1800s?",  # not a year: has a suffix
        "What's her favorite unchanged recipe?",  # "changed" inside another word
        "What does she use to edit photos?",  # "use to", but not about the past
    ],
)
def test_ignores_lookalikes(question: str) -> None:
    assert time_of(plan_search(question, TODAY)) == ("now", None)


EPISODE = {"episode"}
PREFERENCE = {"preference"}
ALL = {"fact", "preference", "episode"}


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # Events: past-tense question words that open the question.
        ("When did she move to Lisbon?", EPISODE),
        ("What did Maya do in Berlin?", EPISODE),
        ("How did she do in her half-marathon?", EPISODE),
        ("Where did she travel in October?", EPISODE),
        ("What trips has Maya taken with Sam?", EPISODE),
        ("What happened at the conference?", EPISODE),
        ("When did Theo last visit her?", EPISODE),
        # Likes, dislikes and habits.
        ("Does she like spicy food?", PREFERENCE),
        ("Would she rather work at a startup?", PREFERENCE),
        ("Which design tool does she prefer?", PREFERENCE),
        ("How does she feel about early meetings?", PREFERENCE),
        ("What's her diet these days?", PREFERENCE),
        # The present tense is a habit, not an event.
        ("When does she like to work out?", PREFERENCE),
        # A "why" links a change to the event behind it.
        ("Why did she switch to Figma?", {"episode", "preference"}),
        # Unsure: search everything. Facts are never searched alone.
        ("Where does she live?", ALL),
        ("Who is her manager?", ALL),
        ("Where did she go to university?", ALL),
        # Both cues: an event about a preference.
        ("When did she start to prefer tea?", ALL),
        # The question word decides only when it opens the question.
        ("What's her role, and when did she start?", ALL),
    ],
)
def test_reads_the_record_types(question: str, expected: set[str]) -> None:
    assert plan_search(question, TODAY).types == expected


def period(start: tuple[int, int, int], end: tuple[int, int, int]) -> Period:
    return Period(datetime(*start, tzinfo=UTC), datetime(*end, tzinfo=UTC))


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Where did she travel in October 2025?", period((2025, 10, 1), (2025, 11, 1))),
        ("What did she do in December 2025?", period((2025, 12, 1), (2026, 1, 1))),
        ("What happened in 2024?", period((2024, 1, 1), (2025, 1, 1))),
        ("Where did she go in early 2025?", period((2025, 1, 1), (2025, 5, 1))),
        ("What did she do in late 2025?", period((2025, 9, 1), (2026, 1, 1))),
        ("What did she do last year?", period((2025, 1, 1), (2026, 1, 1))),
        ("Where did she go?", None),
    ],
)
def test_reads_the_period_a_question_names(question: str, expected: Period | None) -> None:
    assert plan_search(question, TODAY).period == expected


@pytest.mark.parametrize(
    ("question", "latest"),
    [
        ("When did she last visit Toronto?", True),
        ("What was her most recent trip?", True),
        ("What's the latest talk she gave?", True),
        ("Has she travelled recently?", True),
        ("What did she do last year?", False),  # a date, not "the most recent"
        ("What did she do last week?", False),
        ("When did she move to Lisbon?", False),
    ],
)
def test_reads_whether_the_question_wants_the_latest(question: str, latest: bool) -> None:
    assert plan_search(question, TODAY).latest is latest
