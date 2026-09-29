from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from .db import Repository
from .garmin import GarminGateway, map_activity


@dataclass(frozen=True)
class SyncResult:
    sync_id: str
    fetched_count: int
    added_count: int
    updated_count: int
    skipped_count: int


class SyncService:
    def __init__(self, repository: Repository, garmin: GarminGateway):
        self.repository = repository
        self.garmin = garmin

    def run(self, start_date: date, end_date: date) -> SyncResult:
        sync_id = self.repository.begin_sync(start_date.isoformat(), end_date.isoformat())
        try:
            raw = self.garmin.fetch_activities(start_date, end_date)
            mapped: list[dict[str, Any]] = []
            skipped = 0
            for activity in raw:
                try:
                    mapped.append(map_activity(activity))
                except (TypeError, ValueError, OverflowError):
                    skipped += 1

            ids = [row["garmin_activity_id"] for row in mapped]
            existing = self.repository.existing_activity_ids(ids)
            self.repository.upsert_activities(mapped)
            added = len(set(ids) - existing)
            updated = len(set(ids) & existing)
            self.repository.finish_sync(
                sync_id,
                status="success",
                fetched_count=len(raw),
                added_count=added,
                updated_count=updated,
                skipped_count=skipped,
                error_message=None,
            )
            return SyncResult(sync_id, len(raw), added, updated, skipped)
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.repository.finish_sync(
                    sync_id,
                    status="failed",
                    error_message=str(exc)[:1000],
                )
            raise
