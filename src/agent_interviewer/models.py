"""Pydantic models for session state and feedback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Turn(BaseModel):
    """A single exchange in the interview transcript."""

    role: Literal["interviewer", "candidate"]
    text: str
    timestamp: datetime = Field(default_factory=_utc_now)


class Session(BaseModel):
    """The full state of an interview session."""

    id: str
    persona: str
    started_at: datetime = Field(default_factory=_utc_now)
    turns: list[Turn] = Field(default_factory=list)

    def to_claude_history(self) -> list[dict]:
        """Convert turns to the alternating user/assistant format Claude expects."""
        messages: list[dict] = []
        for turn in self.turns:
            role = "assistant" if turn.role == "interviewer" else "user"
            messages.append({"role": role, "content": turn.text})
        return messages


class DimensionScore(BaseModel):
    dimension: str = Field(description="The evaluation dimension, exactly as provided.")
    score: int = Field(
        ge=1,
        le=5,
        description="1 = weak (needs significant work), 5 = strong (ready-to-hire signal).",
    )
    observation: str = Field(
        description="One-sentence concrete observation from the transcript supporting the score."
    )
    suggestion: str = Field(description="One actionable thing the candidate can try next time.")


class Feedback(BaseModel):
    overall: str = Field(description="2-3 sentence overall read on the candidate's performance.")
    dimensions: list[DimensionScore]
    strengths: list[str] = Field(description="2-3 specific strengths observed.", min_length=1)
    growth_areas: list[str] = Field(description="2-3 specific things to work on.", min_length=1)
    mock_recommendation: Literal["needs-more-prep", "borderline", "ready-to-interview"] = Field(
        description="Overall judgment if this were the real interview."
    )
