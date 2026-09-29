
import pytest

from myfitness.garmin import map_activity


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
