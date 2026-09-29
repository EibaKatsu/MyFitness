from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from .db import Repository
from .garmin import (
    GarminGateway,
    GarminNetworkError,
    GarminRateLimitError,
    GarminTokenError,
    calculate_aerobic_decoupling,
    map_activity,
    map_activity_detail_summary,
    map_gear,
    map_hr_zones,
    map_laps,
    map_samples,
    map_weather,
)


@dataclass(frozen=True)
class SyncResult:
    sync_id: str
    fetched_count: int
    added_count: int
    updated_count: int
    skipped_count: int
    detail_synced_count: int = 0
    detail_failed_count: int = 0
    detail_has_more: bool = False


class SyncService:
    def __init__(self, repository: Repository, garmin: GarminGateway, detail_limit: int = 10):
        self.repository = repository
        self.garmin = garmin
        self.detail_limit = detail_limit

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
            candidates = self.repository.detail_sync_candidates(ids, self.detail_limit + 1)
            detail_has_more = len(candidates) > self.detail_limit
            detail_synced = 0
            detail_failed = 0
            for candidate in candidates[: self.detail_limit]:
                activity_uuid = candidate["id"]
                garmin_activity_id = int(candidate["garmin_activity_id"])
                try:
                    bundle = self.garmin.fetch_activity_bundle(garmin_activity_id)
                    summary = map_activity_detail_summary(bundle.summary)
                    samples = map_samples(bundle.details)
                    summary["aerobic_decoupling_pct"] = calculate_aerobic_decoupling(samples)
                    warning = (
                        "取得できなかった任意項目: " + ", ".join(bundle.warnings)
                        if bundle.warnings
                        else None
                    )
                    self.repository.save_activity_details(
                        activity_uuid,
                        summary,
                        map_laps(bundle.splits),
                        map_hr_zones(bundle.hr_zones),
                        samples,
                        map_weather(bundle.weather),
                        map_gear(bundle.gear),
                        warning,
                    )
                    detail_synced += 1
                except (GarminRateLimitError, GarminTokenError):
                    raise
                except GarminNetworkError as detail_exc:
                    self.repository.mark_activity_detail_error(activity_uuid, str(detail_exc))
                    detail_failed += 1
                    break
                except (TypeError, ValueError, OverflowError) as detail_exc:
                    self.repository.mark_activity_detail_error(
                        activity_uuid, f"詳細データの変換に失敗しました: {detail_exc}"
                    )
                    detail_failed += 1
            self.repository.finish_sync(
                sync_id,
                status="success",
                fetched_count=len(raw),
                added_count=added,
                updated_count=updated,
                skipped_count=skipped,
                detail_synced_count=detail_synced,
                detail_failed_count=detail_failed,
                error_message=None,
            )
            return SyncResult(
                sync_id,
                len(raw),
                added,
                updated,
                skipped,
                detail_synced,
                detail_failed,
                detail_has_more,
            )
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.repository.finish_sync(
                    sync_id,
                    status="failed",
                    error_message=str(exc)[:1000],
                )
            raise
