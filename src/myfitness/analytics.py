from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

RUN_TYPES = {"running", "trail_running"}


def build_growth_metrics(
    activities: list[dict[str, Any]], *, period_days: int | None
) -> dict[str, Any]:
    """Build weekly running trends while retaining an all-time fixed baseline."""
    runs = [row for row in activities if row.get("activity_type") in RUN_TYPES]
    runs.sort(key=lambda row: row.get("start_time") or "")
    eligible = [row for row in runs if _aerobic_efficiency(row) is not None]
    baseline_values = [_aerobic_efficiency(row) for row in eligible[:6]]
    baseline = median(baseline_values) if baseline_values else None

    cutoff = None
    if period_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=period_days)
    visible = [row for row in runs if cutoff is None or _datetime(row) >= cutoff]

    weeks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in visible:
        activity_date = _datetime(row).date()
        week_start = activity_date - timedelta(days=activity_date.weekday())
        weeks[week_start.isoformat()].append(row)

    points = []
    for week, rows in sorted(weeks.items()):
        efficiencies = [
            value for row in rows if (value := _aerobic_efficiency(row)) is not None
        ]
        decoupling = [
            float(row["aerobic_decoupling_pct"])
            for row in rows
            if row.get("aerobic_decoupling_pct") is not None
        ]
        efficiency_index = None
        if baseline and efficiencies:
            efficiency_index = median(efficiencies) / baseline * 100
        points.append(
            {
                "date": week,
                "efficiency_index": _round(efficiency_index, 1),
                "weekly_distance_km": _round(
                    sum(float(row.get("distance_m") or 0) for row in rows) / 1000, 1
                ),
                "weekly_elevation_m": _round(
                    sum(float(row.get("elevation_gain_m") or 0) for row in rows), 0
                ),
                "decoupling_pct": _round(median(decoupling), 1) if decoupling else None,
                "activity_count": len(rows),
            }
        )

    latest_indexes = [
        point["efficiency_index"]
        for point in points
        if point["efficiency_index"] is not None
    ]
    return {
        "points": points,
        "baseline_activity_count": len(baseline_values),
        "latest_efficiency_index": latest_indexes[-1] if latest_indexes else None,
        "eligible_activity_count": len(eligible),
        "definitions": {
            "efficiency_index": (
                "勾配補正速度（なければ平均速度）÷平均心拍。"
                "通常のランニングのうち最初の最大6活動を100とした週間中央値"
            ),
            "weekly_distance_km": "週ごとのランニング／トレイルランニング合計距離",
            "weekly_elevation_m": "週ごとの獲得標高合計",
            "decoupling_pct": "活動前半と後半の心拍÷速度比の変化。低いほどペース維持力が高い傾向",
        },
    }


def _aerobic_efficiency(row: dict[str, Any]) -> float | None:
    # Trail pace is strongly affected by terrain and is not directly comparable with
    # road running. Keep trail activities in volume/elevation charts, but exclude
    # them from the fixed-baseline aerobic efficiency index.
    if row.get("activity_type") != "running":
        return None
    duration = _float(row.get("duration_s"))
    distance = _float(row.get("distance_m"))
    heart_rate = _float(row.get("avg_hr"))
    speed = _float(row.get("avg_grade_adjusted_speed_mps")) or _float(
        row.get("avg_speed_mps")
    )
    if (
        duration is None
        or duration < 1200
        or distance is None
        or distance < 3000
        or heart_rate is None
        or not 80 <= heart_rate <= 220
        or speed is None
        or speed <= 0
    ):
        return None
    return speed / heart_rate


def _datetime(row: dict[str, Any]) -> datetime:
    value = str(row["start_time"]).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None
