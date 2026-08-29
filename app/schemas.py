import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
