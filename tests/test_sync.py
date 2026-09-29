from datetime import date

import pytest

from myfitness.garmin import GarminRateLimitError
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


class FakeGarmin:
    def __init__(self, result=None, error=None):
        self.result = result or []
        self.error = error

    def fetch_activities(self, start_date, end_date):
        if self.error:
            raise self.error
        return self.result


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
