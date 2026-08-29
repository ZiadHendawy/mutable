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
    yield db
