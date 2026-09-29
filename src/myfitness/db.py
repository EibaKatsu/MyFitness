from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx


class DatabaseError(RuntimeError):
    pass


class Repository(Protocol):
    def begin_sync(self, start_date: str, end_date: str) -> str: ...
    def finish_sync(self, sync_id: str, **values: Any) -> None: ...
    def existing_activity_ids(self, ids: list[int]) -> set[int]: ...
    def upsert_activities(self, rows: list[dict[str, Any]]) -> None: ...
    def detail_sync_candidates(self, ids: list[int], limit: int) -> list[dict[str, Any]]: ...
    def save_activity_details(
        self,
        activity_id: str,
        summary: dict[str, Any],
        laps: list[dict[str, Any]],
        zones: list[dict[str, Any]],
        samples: list[dict[str, Any]],
        weather: dict[str, Any] | None,
        gear: list[dict[str, Any]],
        warning: str | None,
    ) -> None: ...
    def mark_activity_detail_error(self, activity_id: str, message: str) -> None: ...


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SupabaseRepository:
    """Minimal server-side PostgREST client using the project's secret key."""

    def __init__(self, url: str, secret_key: str, *, client: httpx.Client | None = None):
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.client = client or httpx.Client(timeout=30.0)
        self.headers = {
            "apikey": secret_key,
            "Content-Type": "application/json",
        }
        # New sb_secret_* keys are API keys, not JWTs. Legacy service_role keys
        # still need to be the bearer token so PostgREST assumes service_role.
        if not secret_key.startswith("sb_secret_"):
            self.headers["Authorization"] = f"Bearer {secret_key}"

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            response = self.client.request(
                method, f"{self.base_url}/{path}", headers=headers, **kwargs
            )
            response.raise_for_status()
            return response
        except (httpx.HTTPError, OSError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            hint = f" (HTTP {status})" if status else ""
            raise DatabaseError(f"Supabaseへの接続またはDB操作に失敗しました{hint}。") from exc

    def begin_sync(self, start_date: str, end_date: str) -> str:
        response = self._request(
            "POST",
            "sync_history",
            params={"select": "id"},
            headers={"Prefer": "return=representation"},
            json={"status": "running", "range_start": start_date, "range_end": end_date},
        )
        return response.json()[0]["id"]

    def finish_sync(self, sync_id: str, **values: Any) -> None:
        self._request(
            "PATCH",
            "sync_history",
            params={"id": f"eq.{UUID(sync_id)}"},
            headers={"Prefer": "return=minimal"},
            json={"finished_at": utc_now(), **values},
        )

    def existing_activity_ids(self, ids: list[int]) -> set[int]:
        found: set[int] = set()
        for chunk in _chunks(ids, 200):
            if not chunk:
                continue
            response = self._request(
                "GET",
                "activities",
                params={
                    "select": "garmin_activity_id",
                    "garmin_activity_id": f"in.({','.join(map(str, chunk))})",
                },
            )
            found.update(int(row["garmin_activity_id"]) for row in response.json())
        return found

    def upsert_activities(self, rows: list[dict[str, Any]]) -> None:
        for chunk in _chunks(rows, 200):
            self._request(
                "POST",
                "activities",
                params={"on_conflict": "garmin_activity_id"},
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                json=chunk,
            )

    def detail_sync_candidates(self, ids: list[int], limit: int) -> list[dict[str, Any]]:
        if not ids:
            return []
        response = self._request(
            "GET",
            "activities",
            params={
                "select": "id,garmin_activity_id,start_time",
                "garmin_activity_id": f"in.({','.join(map(str, ids))})",
                "activity_type": "in.(running,trail_running)",
                "details_synced_at": "is.null",
                "order": "start_time.desc",
                "limit": str(limit),
            },
        )
        return response.json()

    def save_activity_details(
        self,
        activity_id: str,
        summary: dict[str, Any],
        laps: list[dict[str, Any]],
        zones: list[dict[str, Any]],
        samples: list[dict[str, Any]],
        weather: dict[str, Any] | None,
        gear: list[dict[str, Any]],
        warning: str | None,
    ) -> None:
        activity_uuid = str(UUID(activity_id))
        self._upsert_related("activity_laps", activity_uuid, laps, "activity_id,lap_index")
        self._upsert_related(
            "activity_hr_zones", activity_uuid, zones, "activity_id,zone_number"
        )
        self._upsert_related(
            "activity_samples", activity_uuid, samples, "activity_id,sample_index", chunk_size=500
        )
        self._upsert_related(
            "activity_gear", activity_uuid, gear, "activity_id,gear_uuid"
        )
        if weather:
            self._upsert_related(
                "activity_weather", activity_uuid, [weather], "activity_id"
            )
        self._request(
            "PATCH",
            "activities",
            params={"id": f"eq.{activity_uuid}"},
            headers={"Prefer": "return=minimal"},
            json={
                **summary,
                "details_synced_at": utc_now(),
                "detail_sync_error": warning,
            },
        )

    def mark_activity_detail_error(self, activity_id: str, message: str) -> None:
        self._request(
            "PATCH",
            "activities",
            params={"id": f"eq.{UUID(activity_id)}"},
            headers={"Prefer": "return=minimal"},
            json={"detail_sync_error": message[:1000]},
        )

    def _upsert_related(
        self,
        table: str,
        activity_id: str,
        rows: list[dict[str, Any]],
        conflict: str,
        *,
        chunk_size: int = 200,
    ) -> None:
        for chunk in _chunks(rows, chunk_size):
            payload = [{"activity_id": activity_id, **row} for row in chunk]
            self._request(
                "POST",
                table,
                params={"on_conflict": conflict},
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                json=payload,
            )

    def list_rows(self, table: str, *, limit: int = 500) -> list[dict[str, Any]]:
        response = self._request(
            "GET", table, params={"select": "*", "order": "recorded_at.desc", "limit": str(limit)}
        )
        return response.json()

    def list_activities(self, *, limit: int = 500) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "activities",
            params={"select": "*", "order": "start_time.desc", "limit": str(limit)},
        )
        return response.json()

    def get_activity_detail(self, row_id: str) -> dict[str, Any]:
        activity_uuid = str(UUID(row_id))
        response = self._request(
            "GET", "activities", params={"select": "*", "id": f"eq.{activity_uuid}"}
        )
        rows = response.json()
        if not rows:
            raise DatabaseError("対象の活動が見つかりません。")
        return {
            "activity": rows[0],
            "laps": self._related_rows("activity_laps", activity_uuid, "lap_index.asc"),
            "hr_zones": self._related_rows(
                "activity_hr_zones", activity_uuid, "zone_number.asc"
            ),
            "weather": self._related_one("activity_weather", activity_uuid),
            "gear": self._related_rows("activity_gear", activity_uuid, "display_name.asc"),
            "annotation": self._related_one("activity_annotations", activity_uuid),
            "samples": self._related_rows(
                "activity_samples", activity_uuid, "sample_index.asc", limit=5000
            ),
        }

    def upsert_activity_annotation(
        self, activity_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        activity_uuid = str(UUID(activity_id))
        response = self._request(
            "POST",
            "activity_annotations",
            params={"on_conflict": "activity_id", "select": "*"},
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json={"activity_id": activity_uuid, **values},
        )
        return response.json()[0]

    def _related_rows(
        self, table: str, activity_id: str, order: str, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_size = 1000
        for start in range(0, limit, page_size):
            response = self._request(
                "GET",
                table,
                params={
                    "select": "*",
                    "activity_id": f"eq.{activity_id}",
                    "order": order,
                },
                headers={"Range": f"{start}-{min(start + page_size - 1, limit - 1)}"},
            )
            page = response.json()
            rows.extend(page)
            if len(page) < page_size:
                break
        return rows

    def _related_one(self, table: str, activity_id: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            table,
            params={"select": "*", "activity_id": f"eq.{activity_id}", "limit": "1"},
        )
        rows = response.json()
        return rows[0] if rows else None

    def list_syncs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "sync_history",
            params={"select": "*", "order": "started_at.desc", "limit": str(limit)},
        )
        return response.json()

    def create_row(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            table,
            headers={"Prefer": "return=representation"},
            params={"select": "*"},
            json=values,
        )
        return response.json()[0]

    def update_row(self, table: str, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "PATCH",
            table,
            headers={"Prefer": "return=representation"},
            params={"id": f"eq.{UUID(row_id)}", "select": "*"},
            json=values,
        )
        rows = response.json()
        if not rows:
            raise DatabaseError("対象データが見つかりません。")
        return rows[0]

    def delete_row(self, table: str, row_id: str) -> None:
        self._request(
            "DELETE",
            table,
            headers={"Prefer": "return=minimal"},
            params={"id": f"eq.{UUID(row_id)}"},
        )


def _chunks(items: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
