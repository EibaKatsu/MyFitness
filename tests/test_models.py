from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from myfitness.models import ActivityAnnotationInput, MealInput, SyncRequest


def test_meal_optional_nutrients_remain_null():
    meal = MealInput(
        recorded_at=datetime(2026, 9, 1, tzinfo=UTC),
        meal_type="lunch",
        description="おにぎり",
    )
    assert meal.calories_kcal is None
    assert meal.protein_g is None
    assert meal.fat_g is None
    assert meal.carbs_g is None


def test_datetime_requires_timezone():
    with pytest.raises(ValidationError, match="タイムゾーン"):
        MealInput(
            recorded_at=datetime(2026, 9, 1, 12, 0),
            meal_type="lunch",
            description="おにぎり",
        )


def test_sync_rejects_reversed_dates():
    with pytest.raises(ValidationError, match="開始日"):
        SyncRequest(start_date="2026-09-02", end_date="2026-09-01")


def test_activity_annotation_validates_rpe():
    with pytest.raises(ValidationError):
        ActivityAnnotationInput(session_rpe=11)
