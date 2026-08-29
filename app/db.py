import uuid
from collections.abc import Generator

from fastapi import Depends, Header
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant_id(x_tenant_id: uuid.UUID = Header(...)) -> uuid.UUID:
    return x_tenant_id


def get_tenant_db(
    tenant_id: uuid.UUID = Depends(get_tenant_id), db: Session = Depends(get_db)
) -> Generator[Session, None, None]:
    # set_config(), not "SET LOCAL ... = :param" -- SET is a utility command
    # and doesn't accept bound parameters the way a normal query does.
    # is_local=true scopes it to this transaction, same as SET LOCAL, so it
    # can't leak into whatever request reuses this pooled connection next.
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    # No signup flow: a tenant becomes real the first time it's used, not
    # through a separate registration step. Safe because tenants has the
    # same RLS policy as everything else -- a caller can only ever insert
    # a row whose id matches the app.tenant_id they just set, i.e. only
    # ever "register" as themselves.
    db.execute(
        text("INSERT INTO tenants (id) VALUES (:tenant_id) ON CONFLICT (id) DO NOTHING"),
        {"tenant_id": str(tenant_id)},
    )
    # Owns the whole transaction on purpose: set_config's scope ends the
    # moment this transaction commits, so committing early (e.g. right
    # after the tenant self-insert) would reset app.tenant_id before the
    # endpoint's own queries ran. Commit once, at the end, so registration
    # and the endpoint's own writes land atomically together.
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
