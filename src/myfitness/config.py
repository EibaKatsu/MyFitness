from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required local configuration is missing or unsafe."""


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    garmin_token_store: Path
    log_level: str = "INFO"
    detail_sync_limit: int = 10

    @classmethod
    def from_env(cls, *, require_supabase: bool = True) -> Settings:
        load_dotenv()
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
        if require_supabase and (not url or not key):
            raise ConfigurationError(
                "SUPABASE_URL と SUPABASE_SECRET_KEY を .env に設定してください。"
            )
        if url and not url.startswith("https://"):
            raise ConfigurationError("SUPABASE_URL は https:// で始まる必要があります。")

        token_store = Path(
            os.getenv("GARMIN_TOKEN_STORE", "~/.garminconnect_myfitness")
        ).expanduser()
        if not token_store.is_absolute():
            raise ConfigurationError(
                "GARMIN_TOKEN_STORE は絶対パスまたは ~/ 配下を指定してください。"
            )
        try:
            detail_sync_limit = int(os.getenv("MYFITNESS_DETAIL_SYNC_LIMIT", "10"))
        except ValueError as exc:
            raise ConfigurationError(
                "MYFITNESS_DETAIL_SYNC_LIMIT は整数で指定してください。"
            ) from exc
        if not 1 <= detail_sync_limit <= 50:
            raise ConfigurationError("MYFITNESS_DETAIL_SYNC_LIMIT は1〜50で指定してください。")
        return cls(
            supabase_url=url,
            supabase_secret_key=key,
            garmin_token_store=token_store,
            log_level=os.getenv("MYFITNESS_LOG_LEVEL", "INFO").upper(),
            detail_sync_limit=detail_sync_limit,
        )
