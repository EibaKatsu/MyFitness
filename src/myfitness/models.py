from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class SyncRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_range(self) -> SyncRequest:
        today = datetime.now(UTC).date()
        self.end_date = self.end_date or today
        self.start_date = self.start_date or (self.end_date - timedelta(days=89))
        if self.start_date > self.end_date:
            raise ValueError("開始日は終了日以前にしてください。")
        if (self.end_date - self.start_date).days > 3660:
            raise ValueError("一度に同期できる期間は最大10年です。")
        return self


class WeightInput(BaseModel):
    recorded_at: datetime
    weight_kg: float = Field(gt=0, le=500)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("recorded_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("日時にはタイムゾーンが必要です。")
        return value

    @field_validator("note")
    @classmethod
    def blank_note_is_null(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    OTHER = "other"


class MealInput(BaseModel):
    recorded_at: datetime
    meal_type: MealType
    description: str = Field(min_length=1, max_length=5000)
    calories_kcal: float | None = Field(default=None, ge=0, le=100000)
    protein_g: float | None = Field(default=None, ge=0, le=10000)
    fat_g: float | None = Field(default=None, ge=0, le=10000)
    carbs_g: float | None = Field(default=None, ge=0, le=10000)

    @field_validator("recorded_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("日時にはタイムゾーンが必要です。")
        return value

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容を入力してください。")
        return value
