import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator


class MemoryFactCreate(BaseModel):
    content: str
    confidence: float = Field(ge=0, le=1)
    source: str | None = None


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
    content: str
    confidence: float = Field(ge=0, le=1)
    strength: float = Field(ge=-1, le=1)
    source: str | None = None
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
    content: str
    confidence: float = Field(ge=0, le=1)
    event_time: datetime
    event_time_end: datetime | None = None
    source: str | None = None

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
