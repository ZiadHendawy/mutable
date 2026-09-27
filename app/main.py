from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import TENANT_DB, get_db
from app.routers import episodes, facts, preferences

app = FastAPI(title="Mutable")
app.include_router(facts.router)
app.include_router(preferences.router)
app.include_router(episodes.router)


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
