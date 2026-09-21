from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class AuthSettings(BaseSettings):
    github_client_id: str = Field(default="", validation_alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", validation_alias="GITHUB_CLIENT_SECRET")
    auth_secret: str = Field(
        default="DIFFLY_INSECURE_DEV_SECRET_KEY_CHANGE_IN_PRODUCTION",
        validation_alias="AUTH_SECRET",
    )
    jwt_lifetime_seconds: int = Field(default=3600 * 24 * 7)  # 7 days

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


auth_settings = AuthSettings()
