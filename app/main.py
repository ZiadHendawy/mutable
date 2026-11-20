from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import TENANT_DB, get_db
from app.embeddings import get_embedder
from app.routers import episodes, facts, preferences, search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Load the embedding model before the server accepts requests, so no caller's first
    # request waits seconds for it. Uvicorn finishes starting, and /health answers, only
    # once this is done. Tests swap in the fake embedder, so this loads nothing for them.
    embedder = app.dependency_overrides.get(get_embedder, get_embedder)()
    embedder.embed(["warm up"])
    yield


app = FastAPI(title="Mutable", lifespan=lifespan)
app.include_router(facts.router)
app.include_router(preferences.router)
app.include_router(episodes.router)
app.include_router(search.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/whoami")
def whoami(db: Session = TENANT_DB) -> dict[str, str]:
    tenant_id = db.execute(text("SELECT current_setting('app.tenant_id')")).scalar_one()
    return {"tenant_id": tenant_id}
