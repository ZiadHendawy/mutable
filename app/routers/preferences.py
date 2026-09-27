import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import TENANT_DB, get_tenant_id
from app.models import MemoryPreference
from app.schemas import MemoryPreferenceCreate, MemoryPreferenceRead

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.post("", response_model=MemoryPreferenceRead, status_code=201)
def create_preference(
    payload: MemoryPreferenceCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = TENANT_DB,
) -> MemoryPreference:
    # exclude_none so an omitted valid_from falls through to the server default.
    data = payload.model_dump(exclude={"supersedes"}, exclude_none=True)
    preference = MemoryPreference(tenant_id=tenant_id, **data)
    db.add(preference)
    db.flush()
    db.refresh(preference)

    if payload.supersedes is not None:
        old = db.get(MemoryPreference, payload.supersedes)
        if old is None:
            raise HTTPException(status_code=404, detail="Preference to supersede not found")
        if old.valid_to is not None:
            raise HTTPException(status_code=409, detail="Preference to supersede is already closed")
        if preference.valid_from < old.valid_from:
            raise HTTPException(
                status_code=422,
                detail="Superseding preference cannot be valid before the one it replaces",
            )
        # Close the old record exactly where the new one starts, so the two
        # validity windows tile with no gap or overlap -- a point-in-time
        # query always finds exactly one of them.
        old.valid_to = preference.valid_from
        old.superseded_by = preference.id

    db.flush()
    db.refresh(preference)
    return preference


@router.get("", response_model=list[MemoryPreferenceRead])
def list_preferences(db: Session = TENANT_DB) -> Sequence[MemoryPreference]:
    stmt = (
        select(MemoryPreference)
        .where(MemoryPreference.valid_to.is_(None))
        .order_by(MemoryPreference.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{preference_id}", response_model=MemoryPreferenceRead)
def get_preference(preference_id: uuid.UUID, db: Session = TENANT_DB) -> MemoryPreference:
    preference = db.get(MemoryPreference, preference_id)
    if preference is None:
        raise HTTPException(status_code=404, detail="Preference not found")
    return preference


@router.delete("/{preference_id}", status_code=204)
def delete_preference(preference_id: uuid.UUID, db: Session = TENANT_DB) -> None:
    preference = db.get(MemoryPreference, preference_id)
    if preference is None:
        raise HTTPException(status_code=404, detail="Preference not found")
    # An older version whose superseded_by points here would be left linking to
    # nothing, breaking its history chain. Refuse clearly rather than let the
    # foreign key fail at commit.
    replaced = db.scalar(
        select(MemoryPreference.id).where(MemoryPreference.superseded_by == preference_id)
    )
    if replaced is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Preference replaced an older version ({replaced}); deleting it would "
            "break that version's history",
        )
    db.delete(preference)
