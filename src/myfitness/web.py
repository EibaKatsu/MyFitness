from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

from .analytics import build_growth_metrics
from .config import Settings
from .db import DatabaseError, SupabaseRepository
from .garmin import GarminConnectGateway, GarminError
from .models import ActivityAnnotationInput, MealInput, SyncRequest, WeightInput
from .sync import SyncService

logger = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).parent


def _json_values(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def create_app(
    settings: Settings | None = None,
    *,
    repository_factory: Callable[[], Any] | None = None,
    garmin_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    repository_factory = repository_factory or (
        lambda: SupabaseRepository(settings.supabase_url, settings.supabase_secret_key)
    )
    garmin_factory = garmin_factory or (lambda: GarminConnectGateway(settings.garmin_token_store))

    app = FastAPI(title="MyFitness", version="0.2.0", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    sync_lock = Lock()

    @app.exception_handler(DatabaseError)
    async def database_error_handler(_: Request, exc: DatabaseError):
        logger.warning("Database operation failed: %s", exc)
        return _error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

    @app.exception_handler(GarminError)
    async def garmin_error_handler(_: Request, exc: GarminError):
        logger.warning("Garmin operation failed: %s", exc)
        return _error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        repository = repository_factory()
        return {
            "activities": repository.list_activities(),
            "weights": repository.list_rows("weight_entries"),
            "meals": repository.list_rows("meal_entries"),
            "syncs": repository.list_syncs(),
        }

    @app.post("/api/sync")
    def sync(request: SyncRequest) -> dict[str, Any]:
        assert request.start_date is not None and request.end_date is not None
        if not sync_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="別のGarmin同期が実行中です。")
        try:
            service = SyncService(
                repository_factory(), garmin_factory(), settings.detail_sync_limit
            )
            result = service.run(request.start_date, request.end_date)
            return {
                "sync_id": result.sync_id,
                "fetched_count": result.fetched_count,
                "added_count": result.added_count,
                "updated_count": result.updated_count,
                "skipped_count": result.skipped_count,
                "detail_synced_count": result.detail_synced_count,
                "detail_failed_count": result.detail_failed_count,
                "detail_has_more": result.detail_has_more,
            }
        finally:
            sync_lock.release()

    @app.get("/api/analytics/growth")
    def growth(
        period_days: int = Query(default=180, ge=0, le=3650),
    ) -> dict[str, Any]:
        activities = repository_factory().list_activities(limit=5000)
        return build_growth_metrics(
            activities, period_days=period_days if period_days else None
        )

    @app.get("/api/activities/{row_id}")
    def activity_detail(row_id: str) -> dict[str, Any]:
        return repository_factory().get_activity_detail(row_id)

    @app.put("/api/activities/{row_id}/annotation")
    def update_activity_annotation(
        row_id: str, value: ActivityAnnotationInput
    ) -> dict[str, Any]:
        return repository_factory().upsert_activity_annotation(row_id, _json_values(value))

    @app.post("/api/weights", status_code=status.HTTP_201_CREATED)
    def create_weight(value: WeightInput) -> dict[str, Any]:
        return repository_factory().create_row("weight_entries", _json_values(value))

    @app.put("/api/weights/{row_id}")
    def update_weight(row_id: str, value: WeightInput) -> dict[str, Any]:
        return repository_factory().update_row("weight_entries", row_id, _json_values(value))

    @app.delete("/api/weights/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_weight(row_id: str) -> Response:
        repository_factory().delete_row("weight_entries", row_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/meals", status_code=status.HTTP_201_CREATED)
    def create_meal(value: MealInput) -> dict[str, Any]:
        return repository_factory().create_row("meal_entries", _json_values(value))

    @app.put("/api/meals/{row_id}")
    def update_meal(row_id: str, value: MealInput) -> dict[str, Any]:
        return repository_factory().update_row("meal_entries", row_id, _json_values(value))

    @app.delete("/api/meals/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_meal(row_id: str) -> Response:
        repository_factory().delete_row("meal_entries", row_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


def _error_response(message: str, status_code: int):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": message})
