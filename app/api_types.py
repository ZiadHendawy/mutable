"""The API's request and response bodies: what each endpoint accepts and returns."""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class MemoryFactCreate(BaseModel):
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    source: str | None = None
    valid_from: datetime | None = None


class MemoryFactRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    content: str
    confidence: float
    source: str | None
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime


class MemoryPreferenceCreate(BaseModel):
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    strength: float = Field(ge=-1, le=1)
    source: str | None = None
    valid_from: datetime | None = None
    supersedes: uuid.UUID | None = None


class MemoryPreferenceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    content: str
    confidence: float
    strength: float
    superseded_by: uuid.UUID | None
    source: str | None
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime


class MemoryEpisodeCreate(BaseModel):
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    event_time: datetime
    event_time_end: datetime | None = None
    source: str | None = None
    valid_from: datetime | None = None

    @model_validator(mode="after")
    def check_time_order(self) -> Self:
        if self.event_time_end is not None and self.event_time_end < self.event_time:
            raise ValueError("event_time_end must not be before event_time")
        return self


class MemoryEpisodeRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    content: str
    confidence: float
    event_time: datetime
    event_time_end: datetime | None
    source: str | None
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime


class SearchResult(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    type: Literal["fact", "preference", "episode"]
    content: str
    score: float  # how well it matches the question; higher is better
    valid_from: datetime
    valid_to: datetime | None
    event_time: datetime | None  # episodes only


class PeriodRead(BaseModel):
    model_config = {"from_attributes": True}

    start: datetime  # inclusive
    end: datetime  # exclusive


class SearchPlanRead(BaseModel):
    """What the search decided to look at, read from the question (app/search_plan.py)."""

    model_config = {"from_attributes": True}

    types: list[Literal["fact", "preference", "episode"]]  # ranked ahead of the others
    time: Literal["now", "as_of", "history"]
    as_of: datetime | None  # set when time is "as_of"
    period: PeriodRead | None  # episodes must overlap it
    latest: bool  # the most recent events are ranked higher

    @field_validator("types", mode="before")
    @classmethod
    def sorted_types(cls, types: Iterable[str]) -> list[str]:
        # The plan keeps them as a set; a sorted list reads the same in every response.
        return sorted(types)


class SearchResponse(BaseModel):
    plan: SearchPlanRead
    results: list[SearchResult]  # best first
