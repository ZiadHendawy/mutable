"""plan_search: the rules that read a question's time scope. Pure functions, no database."""

from datetime import UTC, date, datetime

import pytest

from app.search_plan import SearchPlan, plan_search

TODAY = date(2026, 11, 20)


def as_of(year: int, month: int, day: int) -> SearchPlan:
    return SearchPlan(time="as_of", as_of=datetime(year, month, day, tzinfo=UTC))


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
    assert plan_search(question, TODAY) == expected


def test_a_date_wins_over_a_history_phrase() -> None:
    assert plan_search("What did she use before 2020?", TODAY) == as_of(2020, 7, 1)


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
    assert plan_search(question, TODAY) == SearchPlan()
