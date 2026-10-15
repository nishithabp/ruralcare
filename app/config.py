from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./ruralcare.db"
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 720
    cors_origins: list[str] = ["*"]
    upload_dir: str = "./uploads"

    demo_mode: bool = False             # shows the demo-account buttons on the login screen
    frontend_dir: str = "../frontend"

    max_scans_before_flag: int = 3      # a genuine strip is scanned only a few times
    expiry_warning_days: int = 30
    ring_timeout_seconds: int = 30

    stun_urls: list[str] = ["stun:stun.l.google.com:19302"]
    turn_url: str | None = None
    turn_username: str | None = None
    turn_credential: str | None = None

    sms_provider: str = "console"       # console | twilio
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
