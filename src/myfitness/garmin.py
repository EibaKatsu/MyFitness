from __future__ import annotations

import math
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


class GarminError(RuntimeError):
    pass


class GarminTokenError(GarminError):
    pass


class GarminRateLimitError(GarminError):
    pass


class GarminNetworkError(GarminError):
    pass


class GarminGateway(Protocol):
    def fetch_activities(self, start_date: date, end_date: date) -> list[dict[str, Any]]: ...


class GarminConnectGateway:
    """Thin boundary around the unofficial garminconnect package."""

    def __init__(self, token_store: Path):
        self.token_store = token_store

    def fetch_activities(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        try:
            client = Garmin()
            client.login(str(self.token_store))
            return client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
        except GarminConnectTooManyRequestsError as exc:
            raise GarminRateLimitError(
                "Garminから429が返されました。時間を置いてから再実行してください。"
            ) from exc
        except (GarminConnectAuthenticationError, FileNotFoundError) as exc:
            raise GarminTokenError(
                "Garminトークンが無効です。ターミナルで "
                "`myfitness garmin-login` を実行してください。"
            ) from exc
        except (GarminConnectConnectionError, OSError) as exc:
            message = str(exc)
            if "429" in message:
                raise GarminRateLimitError(
                    "Garminから429が返されました。時間を置いてから再実行してください。"
                ) from exc
            raise GarminNetworkError("Garminとの通信に失敗しました。") from exc


def login_interactively(token_store: Path, email: str, password: str, prompt_mfa: Any) -> None:
    """Authenticate once and persist only Garmin-issued tokens."""
    token_store.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(token_store, 0o700)
    try:
        client = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
        client.login(str(token_store))
    except GarminConnectTooManyRequestsError as exc:
        raise GarminRateLimitError(
            "ログイン試行が制限されました。再試行を繰り返さず、時間を置いてください。"
        ) from exc
    except GarminConnectAuthenticationError as exc:
        raise GarminTokenError(
            "Garmin認証に失敗しました。入力内容またはMFAを確認してください。"
        ) from exc
    except GarminConnectConnectionError as exc:
        raise GarminNetworkError("Garminとの通信に失敗しました。") from exc
    finally:
        password = ""  # Reduce the lifetime of the reference in this frame.

    for path in token_store.iterdir():
        if path.is_file() and not path.is_symlink():
            os.chmod(path, 0o600)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return round(number) if number is not None else None


def _utc_timestamp(activity: dict[str, Any]) -> str:
    raw = activity.get("startTimeGMT") or activity.get("startTimeGmt")
    if raw:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()

    local = activity.get("startTimeLocal")
    if not local:
        raise ValueError("活動に開始日時がありません。")
    parsed = datetime.fromisoformat(str(local).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(UTC).isoformat()


def map_activity(activity: dict[str, Any]) -> dict[str, Any]:
    """Map unstable Garmin JSON into the stable database contract."""
    activity_id = activity.get("activityId")
    if activity_id is None:
        raise ValueError("活動IDがありません。")
    type_data = activity.get("activityType") or {}
    if not isinstance(type_data, dict):
        type_data = {}
    type_key = str(type_data.get("typeKey") or activity.get("activityTypeKey") or "unknown")
    type_label = str(type_data.get("typeName") or type_data.get("typeKey") or type_key)
    return {
        "garmin_activity_id": int(activity_id),
        "start_time": _utc_timestamp(activity),
        "activity_type": type_key,
        "activity_type_label": type_label,
        "activity_name": activity.get("activityName"),
        "distance_m": _number(activity.get("distance")),
        "duration_s": _number(activity.get("duration")),
        "moving_duration_s": _number(activity.get("movingDuration")),
        "avg_hr": _integer(activity.get("averageHR")),
        "max_hr": _integer(activity.get("maxHR")),
        "avg_speed_mps": _number(activity.get("averageSpeed")),
        "elevation_gain_m": _number(activity.get("elevationGain")),
        "calories_kcal": _number(activity.get("calories")),
    }
