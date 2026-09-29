from __future__ import annotations

import math
import os
from dataclasses import dataclass
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

    def fetch_activity_bundle(self, activity_id: int) -> ActivityBundle: ...


@dataclass(frozen=True)
class ActivityBundle:
    summary: dict[str, Any]
    details: dict[str, Any]
    splits: dict[str, Any]
    hr_zones: list[dict[str, Any]]
    weather: dict[str, Any] | None
    gear: list[dict[str, Any]]
    warnings: tuple[str, ...] = ()


class GarminConnectGateway:
    """Thin boundary around the unofficial garminconnect package."""

    def __init__(self, token_store: Path):
        self.token_store = token_store
        self._client: Garmin | None = None

    def _authenticated_client(self) -> Garmin:
        if self._client is not None:
            return self._client
        try:
            client = Garmin()
            client.login(str(self.token_store))
            self._client = client
            return client
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
            self._raise_connection_error(exc)

    @staticmethod
    def _raise_connection_error(exc: Exception) -> None:
        if "429" in str(exc):
            raise GarminRateLimitError(
                "Garminから429が返されました。時間を置いてから再実行してください。"
            ) from exc
        raise GarminNetworkError("Garminとの通信に失敗しました。") from exc

    def _call(self, method: Any, *args: Any) -> Any:
        try:
            return method(*args)
        except GarminConnectTooManyRequestsError as exc:
            raise GarminRateLimitError(
                "Garminから429が返されました。時間を置いてから再実行してください。"
            ) from exc
        except GarminConnectAuthenticationError as exc:
            raise GarminTokenError(
                "Garminトークンが無効です。ターミナルで再認証してください。"
            ) from exc
        except (GarminConnectConnectionError, OSError) as exc:
            self._raise_connection_error(exc)

    def fetch_activities(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        client = self._authenticated_client()
        return self._call(
            client.get_activities_by_date, start_date.isoformat(), end_date.isoformat()
        )

    def fetch_activity_bundle(self, activity_id: int) -> ActivityBundle:
        client = self._authenticated_client()
        activity_id_str = str(activity_id)
        summary = self._call(client.get_activity, activity_id_str)
        details = self._call(client.get_activity_details, activity_id_str)
        splits = self._call(client.get_activity_splits, activity_id_str)
        warnings: list[str] = []

        def optional(name: str, method: Any, default: Any) -> Any:
            try:
                return self._call(method, activity_id_str)
            except (GarminRateLimitError, GarminTokenError):
                raise
            except GarminNetworkError:
                warnings.append(name)
                return default

        return ActivityBundle(
            summary=summary,
            details=details,
            splits=splits,
            hr_zones=optional("心拍ゾーン", client.get_activity_hr_in_timezones, []),
            weather=optional("天候", client.get_activity_weather, None),
            gear=optional("ギア", client.get_activity_gear, []),
            warnings=tuple(warnings),
        )


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
        "elapsed_duration_s": _number(activity.get("elapsedDuration")),
        "avg_hr": _integer(activity.get("averageHR")),
        "max_hr": _integer(activity.get("maxHR")),
        "min_hr": _integer(activity.get("minHR")),
        "avg_speed_mps": _number(activity.get("averageSpeed")),
        "max_speed_mps": _number(activity.get("maxSpeed")),
        "avg_moving_speed_mps": _number(activity.get("averageMovingSpeed")),
        "avg_grade_adjusted_speed_mps": _number(activity.get("avgGradeAdjustedSpeed")),
        "elevation_gain_m": _number(activity.get("elevationGain")),
        "elevation_loss_m": _number(activity.get("elevationLoss")),
        "min_elevation_m": _number(activity.get("minElevation")),
        "avg_elevation_m": _number(activity.get("avgElevation")),
        "max_elevation_m": _number(activity.get("maxElevation")),
        "calories_kcal": _number(activity.get("calories")),
        "avg_run_cadence_spm": _number(activity.get("averageRunCadence")),
        "max_run_cadence_spm": _number(activity.get("maxRunCadence")),
        "avg_power_w": _number(activity.get("averagePower")),
        "max_power_w": _number(activity.get("maxPower")),
        "normalized_power_w": _number(activity.get("normalizedPower")),
        "training_effect": _number(activity.get("trainingEffect")),
        "anaerobic_training_effect": _number(activity.get("anaerobicTrainingEffect")),
        "activity_training_load": _number(activity.get("activityTrainingLoad")),
    }


def map_activity_detail_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summaryDTO") or {}
    metadata = payload.get("metadataDTO") or {}
    device = metadata.get("deviceMetaDataDTO") or {}
    return {
        "elapsed_duration_s": _number(summary.get("elapsedDuration")),
        "avg_moving_speed_mps": _number(summary.get("averageMovingSpeed")),
        "max_speed_mps": _number(summary.get("maxSpeed")),
        "avg_grade_adjusted_speed_mps": _number(summary.get("avgGradeAdjustedSpeed")),
        "min_hr": _integer(summary.get("minHR")),
        "recovery_hr": _integer(summary.get("recoveryHeartRate")),
        "elevation_loss_m": _number(summary.get("elevationLoss")),
        "min_elevation_m": _number(summary.get("minElevation")),
        "avg_elevation_m": _number(summary.get("avgElevation")),
        "max_elevation_m": _number(summary.get("maxElevation")),
        "avg_run_cadence_spm": _number(summary.get("averageRunCadence")),
        "max_run_cadence_spm": _number(summary.get("maxRunCadence")),
        "avg_power_w": _number(summary.get("averagePower")),
        "max_power_w": _number(summary.get("maxPower")),
        "normalized_power_w": _number(summary.get("normalizedPower")),
        "total_work_j": _number(summary.get("totalWork")),
        "steps": _integer(summary.get("steps")),
        "stride_length_cm": _number(summary.get("strideLength")),
        "vertical_oscillation_cm": _number(summary.get("verticalOscillation")),
        "vertical_ratio_pct": _number(summary.get("verticalRatio")),
        "ground_contact_time_ms": _number(summary.get("groundContactTime")),
        "training_effect": _number(summary.get("trainingEffect")),
        "anaerobic_training_effect": _number(summary.get("anaerobicTrainingEffect")),
        "activity_training_load": _number(summary.get("activityTrainingLoad")),
        "training_effect_label": summary.get("trainingEffectLabel"),
        "difference_body_battery": _integer(summary.get("differenceBodyBattery")),
        "workout_rpe": _integer(summary.get("directWorkoutRpe")),
        "workout_feel": _integer(summary.get("directWorkoutFeel")),
        "moderate_intensity_minutes": _integer(summary.get("moderateIntensityMinutes")),
        "vigorous_intensity_minutes": _integer(summary.get("vigorousIntensityMinutes")),
        "water_estimated_ml": _number(summary.get("waterEstimated")),
        "lap_count": _integer(metadata.get("lapCount")),
        "device_manufacturer": metadata.get("manufacturer"),
        "device_id": str(device.get("deviceId")) if device.get("deviceId") else None,
    }


def map_laps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for position, lap in enumerate(payload.get("lapDTOs") or [], start=1):
        result.append(
            {
                "lap_index": _integer(lap.get("lapIndex")) or position,
                "start_time": _optional_utc_timestamp(lap.get("startTimeGMT")),
                "distance_m": _number(lap.get("distance")),
                "duration_s": _number(lap.get("duration")),
                "moving_duration_s": _number(lap.get("movingDuration")),
                "elapsed_duration_s": _number(lap.get("elapsedDuration")),
                "avg_speed_mps": _number(lap.get("averageSpeed")),
                "max_speed_mps": _number(lap.get("maxSpeed")),
                "avg_grade_adjusted_speed_mps": _number(lap.get("avgGradeAdjustedSpeed")),
                "avg_hr": _integer(lap.get("averageHR")),
                "max_hr": _integer(lap.get("maxHR")),
                "avg_run_cadence_spm": _number(lap.get("averageRunCadence")),
                "max_run_cadence_spm": _number(lap.get("maxRunCadence")),
                "avg_power_w": _number(lap.get("averagePower")),
                "max_power_w": _number(lap.get("maxPower")),
                "normalized_power_w": _number(lap.get("normalizedPower")),
                "elevation_gain_m": _number(lap.get("elevationGain")),
                "elevation_loss_m": _number(lap.get("elevationLoss")),
                "stride_length_cm": _number(lap.get("strideLength")),
                "vertical_oscillation_cm": _number(lap.get("verticalOscillation")),
                "vertical_ratio_pct": _number(lap.get("verticalRatio")),
                "ground_contact_time_ms": _number(lap.get("groundContactTime")),
                "intensity_type": lap.get("intensityType"),
            }
        )
    return result


def map_hr_zones(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "zone_number": _integer(row.get("zoneNumber")),
            "low_boundary_bpm": _integer(row.get("zoneLowBoundary")),
            "seconds_in_zone": _number(row.get("secsInZone")),
        }
        for row in rows
        if _integer(row.get("zoneNumber")) is not None
    ]


def map_weather(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    station = payload.get("weatherStationDTO") or {}
    weather_type = payload.get("weatherTypeDTO") or {}
    return {
        "temperature_raw": _number(payload.get("temp")),
        "apparent_temperature_raw": _number(payload.get("apparentTemp")),
        "dew_point_raw": _number(payload.get("dewPoint")),
        "relative_humidity_pct": _number(payload.get("relativeHumidity")),
        "wind_speed_raw": _number(payload.get("windSpeed")),
        "wind_gust_raw": _number(payload.get("windGust")),
        "wind_direction_deg": _number(payload.get("windDirection")),
        "wind_direction_compass": payload.get("windDirectionCompassPoint"),
        "weather_description": weather_type.get("desc"),
        "station_name": station.get("name"),
        "observed_at": _metric_timestamp(payload.get("issueDate")),
    }


def map_gear(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "gear_uuid": str(row.get("uuid")),
            "display_name": row.get("displayName"),
            "gear_type": row.get("gearTypeName"),
            "manufacturer": row.get("gearMakeName"),
            "model": row.get("gearModelName") or row.get("customMakeModel"),
        }
        for row in rows
        if row.get("uuid")
    ]


def map_samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    descriptors = {
        row.get("key"): int(row["metricsIndex"])
        for row in payload.get("metricDescriptors") or []
        if row.get("key") and row.get("metricsIndex") is not None
    }

    def metric(values: list[Any], key: str) -> Any:
        index = descriptors.get(key)
        return values[index] if index is not None and index < len(values) else None

    result = []
    for sample_index, row in enumerate(payload.get("activityDetailMetrics") or []):
        values = row.get("metrics") or []
        result.append(
            {
                "sample_index": sample_index,
                "recorded_at": _metric_timestamp(metric(values, "directTimestamp")),
                "distance_m": _number(metric(values, "sumDistance")),
                "duration_s": _number(metric(values, "sumDuration")),
                "moving_duration_s": _number(metric(values, "sumMovingDuration")),
                "elapsed_duration_s": _number(metric(values, "sumElapsedDuration")),
                "heart_rate_bpm": _integer(metric(values, "directHeartRate")),
                "speed_mps": _number(metric(values, "directSpeed")),
                "grade_adjusted_speed_mps": _number(
                    metric(values, "directGradeAdjustedSpeed")
                ),
                "elevation_m": _number(metric(values, "directElevation")),
                "vertical_speed_mps": _number(metric(values, "directVerticalSpeed")),
                "cadence_spm": _number(
                    metric(values, "directRunCadence")
                    or metric(values, "directDoubleCadence")
                ),
                "power_w": _number(metric(values, "directPower")),
                "body_battery": _integer(metric(values, "directBodyBattery")),
                "stride_length_cm": _number(metric(values, "directStrideLength")),
                "vertical_oscillation_cm": _number(
                    metric(values, "directVerticalOscillation")
                ),
                "vertical_ratio_pct": _number(metric(values, "directVerticalRatio")),
                "ground_contact_time_ms": _number(
                    metric(values, "directGroundContactTime")
                ),
                "performance_condition": _number(
                    metric(values, "directPerformanceCondition")
                ),
            }
        )
    return result


def calculate_aerobic_decoupling(samples: list[dict[str, Any]]) -> float | None:
    valid = [
        row
        for row in samples
        if row.get("heart_rate_bpm")
        and (row.get("grade_adjusted_speed_mps") or row.get("speed_mps"))
    ]
    if len(valid) < 20:
        return None
    midpoint = len(valid) // 2

    def ratio(rows: list[dict[str, Any]]) -> float | None:
        heart_rates = [float(row["heart_rate_bpm"]) for row in rows]
        speeds = [
            float(row.get("grade_adjusted_speed_mps") or row["speed_mps"]) for row in rows
        ]
        avg_speed = sum(speeds) / len(speeds)
        return (sum(heart_rates) / len(heart_rates)) / avg_speed if avg_speed > 0 else None

    first = ratio(valid[:midpoint])
    second = ratio(valid[midpoint:])
    return ((second / first) - 1) * 100 if first and second else None


def _optional_utc_timestamp(raw: Any) -> str | None:
    if raw in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _metric_timestamp(raw: Any) -> str | None:
    number = _number(raw)
    if number is None:
        return _optional_utc_timestamp(raw)
    if number > 100_000_000_000:
        number /= 1000
    return datetime.fromtimestamp(number, UTC).isoformat()
