from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = Field(default="0.0.0.0", alias="XTTS_HOST")
    port: int = Field(default=8020, alias="XTTS_PORT")
    auth_token: str = Field(default="change-me-now", alias="XTTS_AUTH_TOKEN")
    model_name: str = Field(
        default="tts_models/multilingual/multi-dataset/xtts_v2",
        alias="XTTS_MODEL_NAME",
    )
    max_text_chars: int = Field(default=1200, alias="XTTS_MAX_TEXT_CHARS")
    max_audio_seconds: int = Field(default=15, alias="XTTS_MAX_AUDIO_SECONDS")
    max_upload_mb: int = Field(default=10, alias="XTTS_MAX_UPLOAD_MB")
    temp_dir: Path = Field(default=Path("/tmp/xtts-server"), alias="XTTS_TEMP_DIR")
    log_level: str = Field(default="INFO", alias="XTTS_LOG_LEVEL")

    bonjour_service_type: str = Field(default="_xtts._tcp.local.", alias="XTTS_BONJOUR_SERVICE_TYPE")
    bonjour_service_name: str = Field(default="XTTS Server", alias="XTTS_BONJOUR_SERVICE_NAME")
    bonjour_ttl: int = Field(default=60, alias="XTTS_BONJOUR_TTL")
    bonjour_enabled: bool = Field(default=True, alias="XTTS_BONJOUR_ENABLED")
    show_pairing_qr: bool = Field(default=True, alias="XTTS_SHOW_PAIRING_QR")
    pair_host: str = Field(default="", alias="XTTS_PAIR_HOST")

    request_timeout_seconds: int = 90

    # Optional: auto-send each generated clip as iMessage voice note via BlueBubbles.
    imsg_autosend_enabled: bool = Field(default=False, alias="XTTS_IMSG_AUTOSEND_ENABLED")
    imsg_host: str = Field(default="", alias="XTTS_IMSG_HOST")
    imsg_password: str = Field(default="", alias="XTTS_IMSG_PASSWORD")
    imsg_chat_guid: str = Field(default="", alias="XTTS_IMSG_CHAT_GUID")
    imsg_ffmpeg_bin: str = Field(default="ffmpeg", alias="XTTS_IMSG_FFMPEG_BIN")
    imsg_curl_bin: str = Field(default="curl", alias="XTTS_IMSG_CURL_BIN")
    imsg_timeout_seconds: int = Field(default=30, alias="XTTS_IMSG_TIMEOUT_SECONDS")


settings = Settings()
