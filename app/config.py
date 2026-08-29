from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Restricted, non-superuser role — what the running API connects as.
    # RLS policies apply to this role; it can't bypass them.
    database_url: str = (
        "postgresql+psycopg://memory_engine_app:memory_engine_app@localhost:5432/memory_engine"
    )

    # Superuser role — migrations only (needs DDL rights RLS doesn't restrict anyway).
    admin_database_url: str = (
        "postgresql+psycopg://memory_engine:memory_engine@localhost:5432/memory_engine"
    )


settings = Settings()
