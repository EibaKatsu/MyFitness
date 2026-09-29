from datetime import date

import pytest

from myfitness.garmin import ActivityBundle, GarminRateLimitError
from myfitness.sync import SyncService

ACTIVITY = {
    "activityId": 42,
    "startTimeGMT": "2026-09-20T10:00:00Z",
    "activityType": {"typeKey": "running"},
    "distance": 5000,
    "duration": 1500,
}


class FakeRepository:
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.rows = []
        self.finished = []

    def begin_sync(self, start_date, end_date):
        return "11111111-1111-1111-1111-111111111111"

    def finish_sync(self, sync_id, **values):
        self.finished.append(values)

    def existing_activity_ids(self, ids):
        return self.existing.intersection(ids)

    def upsert_activities(self, rows):
        self.rows.extend(rows)

    def detail_sync_candidates(self, ids, limit):
        return []

    def save_activity_details(self, *args, **kwargs):
        raise AssertionError("No detail candidate was expected in this test")

    def mark_activity_detail_error(self, activity_id, message):
        self.detail_error = message


class FakeGarmin:
    def __init__(self, result=None, error=None):
        self.result = result or []
        self.error = error

    def fetch_activities(self, start_date, end_date):
        if self.error:
            raise self.error
        return self.result


class DetailRepository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.saved_details = []

    def detail_sync_candidates(self, ids, limit):
        return [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "garmin_activity_id": 42,
            }
        ]

    def save_activity_details(self, *args):
        self.saved_details.append(args)


class DetailGarmin(FakeGarmin):
    def fetch_activity_bundle(self, activity_id):
        assert activity_id == 42
        descriptors = [
            {"key": "directHeartRate", "metricsIndex": 0},
            {"key": "directSpeed", "metricsIndex": 1},
            {"key": "directLatitude", "metricsIndex": 2},
        ]
        samples = [
            {"metrics": [140 if index < 10 else 147, 4.0, 35.0]}
            for index in range(20)
        ]
        return ActivityBundle(
            summary={"summaryDTO": {"trainingEffect": 3.1}},
            details={
                "metricDescriptors": descriptors,
                "activityDetailMetrics": samples,
            },
            splits={"lapDTOs": [{"lapIndex": 1, "distance": 5000}]},
            hr_zones=[{"zoneNumber": 3, "secsInZone": 600}],
            weather=None,
            gear=[],
        )


def test_existing_activity_is_updated_not_added():
    repository = FakeRepository(existing={42})
    result = SyncService(repository, FakeGarmin([ACTIVITY])).run(
        date(2026, 9, 1), date(2026, 9, 30)
    )
    assert result.added_count == 0
    assert result.updated_count == 1
    assert repository.rows[0]["garmin_activity_id"] == 42
    assert repository.finished[-1]["status"] == "success"


def test_new_activity_is_added():
    repository = FakeRepository()
    result = SyncService(repository, FakeGarmin([ACTIVITY])).run(
        date(2026, 9, 1), date(2026, 9, 30)
    )
    assert result.added_count == 1
    assert result.updated_count == 0


def test_rate_limit_does_not_write_or_retry_and_records_failure():
    repository = FakeRepository(existing={42})
    gateway = FakeGarmin(error=GarminRateLimitError("429: wait"))
    with pytest.raises(GarminRateLimitError):
        SyncService(repository, gateway).run(date(2026, 9, 1), date(2026, 9, 30))
    assert repository.rows == []
    assert repository.finished[-1]["status"] == "failed"
    assert "429" in repository.finished[-1]["error_message"]


def test_detail_bundle_is_mapped_and_saved_without_gps_coordinates():
    repository = DetailRepository()
    result = SyncService(repository, DetailGarmin([ACTIVITY])).run(
        date(2026, 9, 1), date(2026, 9, 30)
    )
    assert result.detail_synced_count == 1
    saved = repository.saved_details[0]
    summary, laps, zones, samples = saved[1:5]
    assert summary["training_effect"] == 3.1
    assert summary["aerobic_decoupling_pct"] == pytest.approx(5.0)
    assert laps[0]["distance_m"] == 5000
    assert zones[0]["zone_number"] == 3
    assert "latitude" not in samples[0]
    assert "longitude" not in samples[0]
