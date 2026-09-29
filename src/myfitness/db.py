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
