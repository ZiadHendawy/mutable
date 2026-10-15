import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import TENANT_DB, get_tenant_id
from app.models import MemoryFact
from app.schemas import MemoryFactCreate, MemoryFactRead

router = APIRouter(prefix="/facts", tags=["facts"])


@router.post("", response_model=MemoryFactRead, status_code=201)
def create_fact(
    payload: MemoryFactCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = TENANT_DB,
) -> MemoryFact:
    fact = MemoryFact(tenant_id=tenant_id, **payload.model_dump(exclude_none=True))
    db.add(fact)
    db.flush()
    db.refresh(fact)
    return fact


@router.get("", response_model=list[MemoryFactRead])
def list_facts(db: Session = TENANT_DB) -> Sequence[MemoryFact]:
    stmt = (
        select(MemoryFact)
        .where(MemoryFact.valid_to.is_(None))
        .order_by(MemoryFact.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{fact_id}", response_model=MemoryFactRead)
def get_fact(fact_id: uuid.UUID, db: Session = TENANT_DB) -> MemoryFact:
    fact = db.get(MemoryFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return fact


@router.delete("/{fact_id}", status_code=204)
def delete_fact(fact_id: uuid.UUID, db: Session = TENANT_DB) -> None:
    fact = db.get(MemoryFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    db.delete(fact)
