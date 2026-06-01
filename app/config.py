from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_base_url: str = "http://localhost:8001"
    database_url: str = "sqlite+aiosqlite:////data/event.db"
    admin_password: str = "change-this-password"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True

    event_max_age_days: int = 548
    done_event_cleanup_days: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
