import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import TENANT_DB, get_tenant_id
from app.models import MemoryEpisode
from app.schemas import MemoryEpisodeCreate, MemoryEpisodeRead

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("", response_model=MemoryEpisodeRead, status_code=201)
def create_episode(
    payload: MemoryEpisodeCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = TENANT_DB,
) -> MemoryEpisode:
    episode = MemoryEpisode(tenant_id=tenant_id, **payload.model_dump(exclude_none=True))
    db.add(episode)
    db.flush()
    db.refresh(episode)
    return episode


@router.get("", response_model=list[MemoryEpisodeRead])
def list_episodes(db: Session = TENANT_DB) -> Sequence[MemoryEpisode]:
    stmt = (
        select(MemoryEpisode)
        .where(MemoryEpisode.valid_to.is_(None))
        .order_by(MemoryEpisode.event_time.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{episode_id}", response_model=MemoryEpisodeRead)
def get_episode(episode_id: uuid.UUID, db: Session = TENANT_DB) -> MemoryEpisode:
    episode = db.get(MemoryEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.delete("/{episode_id}", status_code=204)
def delete_episode(episode_id: uuid.UUID, db: Session = TENANT_DB) -> None:
    episode = db.get(MemoryEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    db.delete(episode)
