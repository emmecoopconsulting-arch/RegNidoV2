from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://regnido_user:change-me-db-password@db:5432/regnido"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    cors_origins: str = "*"

    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_full_name: str = ""


settings = Settings()
