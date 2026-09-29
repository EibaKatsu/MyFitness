from myfitness.analytics import build_growth_metrics


def run(date, distance, speed, heart_rate, elevation=0, decoupling=None):
    return {
        "start_time": f"{date}T06:00:00+00:00",
        "activity_type": "running",
        "distance_m": distance,
        "duration_s": distance / speed,
        "avg_speed_mps": speed,
        "avg_grade_adjusted_speed_mps": None,
        "avg_hr": heart_rate,
        "elevation_gain_m": elevation,
        "aerobic_decoupling_pct": decoupling,
    }


def test_growth_index_uses_fixed_early_baseline():
    activities = [
        run("2026-01-05", 5000, 3.0, 150),
        run("2026-01-12", 5000, 3.0, 150),
        run("2026-01-19", 5000, 3.3, 150),
    ]
    result = build_growth_metrics(activities, period_days=None)
    assert result["baseline_activity_count"] == 3
    assert result["points"][0]["efficiency_index"] == 100.0
    assert result["points"][-1]["efficiency_index"] == 110.0


def test_short_activity_is_excluded_from_efficiency_but_in_weekly_distance():
    activities = [run("2026-01-05", 2000, 3.0, 140)]
    result = build_growth_metrics(activities, period_days=None)
    assert result["eligible_activity_count"] == 0
    assert result["points"][0]["efficiency_index"] is None
    assert result["points"][0]["weekly_distance_km"] == 2.0


def test_trail_is_kept_in_volume_but_excluded_from_road_efficiency():
    activity = run("2026-01-05", 10000, 3.0, 140, elevation=500)
    activity["activity_type"] = "trail_running"
    result = build_growth_metrics([activity], period_days=None)
    assert result["eligible_activity_count"] == 0
    assert result["points"][0]["efficiency_index"] is None
    assert result["points"][0]["weekly_distance_km"] == 10.0
    assert result["points"][0]["weekly_elevation_m"] == 500.0
