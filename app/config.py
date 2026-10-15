from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Restricted, non-superuser role — what the running API connects as.
    # RLS policies apply to this role; it can't bypass them.
    database_url: str = (
        "postgresql+psycopg://mutable_app:mutable_app@localhost:5432/mutable"
    )

    # Superuser role — migrations only (needs DDL rights RLS doesn't restrict anyway).
    admin_database_url: str = (
        "postgresql+psycopg://mutable:mutable@localhost:5432/mutable"
    )


settings = Settings()
