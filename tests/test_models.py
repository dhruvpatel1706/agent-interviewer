"""Tests for pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_interviewer.models import DimensionScore, Feedback


def test_score_range_enforced() -> None:
    with pytest.raises(ValidationError):
        DimensionScore(dimension="x", score=0, observation="a", suggestion="b")
    with pytest.raises(ValidationError):
        DimensionScore(dimension="x", score=6, observation="a", suggestion="b")


def test_feedback_requires_nonempty_lists() -> None:
    with pytest.raises(ValidationError):
        Feedback(
            overall="fine",
            dimensions=[DimensionScore(dimension="x", score=3, observation="a", suggestion="b")],
            strengths=[],
            growth_areas=["clarity"],
            mock_recommendation="borderline",
        )
    with pytest.raises(ValidationError):
        Feedback(
            overall="fine",
            dimensions=[DimensionScore(dimension="x", score=3, observation="a", suggestion="b")],
            strengths=["specifics"],
            growth_areas=[],
            mock_recommendation="borderline",
        )


def test_feedback_recommendation_literal() -> None:
    with pytest.raises(ValidationError):
        Feedback(
            overall="fine",
            dimensions=[DimensionScore(dimension="x", score=3, observation="a", suggestion="b")],
            strengths=["s"],
            growth_areas=["g"],
            mock_recommendation="definitely-hire",  # type: ignore[arg-type]
        )
