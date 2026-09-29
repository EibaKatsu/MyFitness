
import pytest

from myfitness.garmin import (
    calculate_aerobic_decoupling,
    map_activity,
    map_samples,
    map_weather,
)


def test_map_activity_converts_timestamp_and_preserves_metric_units():
    row = map_activity(
        {
            "activityId": 123456,
            "activityName": "Morning Trail",
            "startTimeGMT": "2026-09-20 23:30:00",
            "activityType": {"typeKey": "trail_running", "typeName": "Trail Running"},
            "distance": 12345.6,
            "duration": 3601.2,
            "averageHR": 142.4,
            "maxHR": 178,
            "averageSpeed": 3.428,
        }
    )

    assert row["garmin_activity_id"] == 123456
    assert row["activity_type"] == "trail_running"
    assert row["distance_m"] == pytest.approx(12345.6)
    assert row["duration_s"] == pytest.approx(3601.2)
    assert row["avg_hr"] == 142
    assert row["start_time"].endswith("+00:00")


def test_map_activity_allows_missing_summary_values():
    row = map_activity(
        {
            "activityId": "99",
            "startTimeGMT": "2026-09-20T10:00:00Z",
            "activityType": {"typeKey": "running"},
        }
    )
    assert row["distance_m"] is None
    assert row["avg_hr"] is None
    assert row["activity_type_label"] == "running"


def test_map_activity_rejects_missing_id():
    with pytest.raises(ValueError, match="活動ID"):
        map_activity({"startTimeGMT": "2026-09-20T10:00:00Z"})


def test_map_samples_uses_descriptors_and_excludes_coordinates():
    payload = {
        "metricDescriptors": [
            {"key": "directTimestamp", "metricsIndex": 0},
            {"key": "sumDistance", "metricsIndex": 1},
            {"key": "directHeartRate", "metricsIndex": 2},
            {"key": "directSpeed", "metricsIndex": 3},
            {"key": "directLatitude", "metricsIndex": 4},
            {"key": "directLongitude", "metricsIndex": 5},
        ],
        "activityDetailMetrics": [
            {"metrics": [1_790_000_000_000, 1000.0, 140.0, 3.5, 35.0, 139.0]}
        ],
    }
    rows = map_samples(payload)
    assert rows[0]["distance_m"] == 1000.0
    assert rows[0]["heart_rate_bpm"] == 140
    assert rows[0]["speed_mps"] == 3.5
    assert "latitude" not in rows[0]
    assert "longitude" not in rows[0]
    assert rows[0]["recorded_at"].endswith("+00:00")


def test_decoupling_compares_second_half_hr_to_speed_ratio():
    samples = [
        {"heart_rate_bpm": 140, "speed_mps": 4.0} for _ in range(10)
    ] + [{"heart_rate_bpm": 154, "speed_mps": 4.0} for _ in range(10)]
    assert calculate_aerobic_decoupling(samples) == pytest.approx(10.0)


def test_weather_accepts_epoch_timestamp_and_excludes_coordinates():
    weather = map_weather(
        {
            "issueDate": 1_790_000_000_000,
            "temp": 20,
            "latitude": 35.0,
            "longitude": 139.0,
        }
    )
    assert weather is not None
    assert weather["observed_at"].endswith("+00:00")
    assert "latitude" not in weather
    assert "longitude" not in weather
