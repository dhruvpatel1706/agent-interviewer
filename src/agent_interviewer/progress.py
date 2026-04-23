"""Longitudinal analysis across past sessions — per-dimension score trends.

Reads the existing JSONL transcripts + their .feedback.json sidecars. No new
storage format. A sessions dir with N (transcript, feedback) pairs turns into
a single "here's how you're improving on system-design interviews" view.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent_interviewer.models import Feedback
from agent_interviewer.storage import load_session


@dataclass
class SessionRecord:
    session_id: str
    persona: str
    when: datetime
    feedback: Feedback


@dataclass
class DimensionTrend:
    dimension: str
    scores: list[tuple[datetime, int]]  # oldest first
    mean: float
    latest: int
    delta: float  # latest - mean of everything before latest (0.0 if <2 sessions)


def _feedback_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.feedback.json"


def _session_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.jsonl"


def load_records(sessions_dir: Path) -> list[SessionRecord]:
    """Load every session that has both a transcript and a feedback sidecar."""
    if not sessions_dir.exists():
        return []
    records: list[SessionRecord] = []
    for feedback_file in sorted(sessions_dir.glob("*.feedback.json")):
        session_id = feedback_file.stem.removesuffix(".feedback")
        session_file = _session_path(sessions_dir, session_id)
        if not session_file.exists():
            continue
        try:
            feedback = Feedback.model_validate_json(feedback_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            continue
        # Pull persona + start time from the transcript.
        sess = load_session(sessions_dir, session_id, persona="behavioral")
        if not sess.turns:
            continue
        records.append(
            SessionRecord(
                session_id=session_id,
                persona=sess.persona,
                when=sess.turns[0].timestamp,
                feedback=feedback,
            )
        )
    records.sort(key=lambda r: r.when)
    return records


def dimension_trends(records: list[SessionRecord]) -> dict[str, DimensionTrend]:
    """Collect per-dimension score series from the given records."""
    if not records:
        return {}

    by_dim: dict[str, list[tuple[datetime, int]]] = {}
    for rec in records:
        for d in rec.feedback.dimensions:
            by_dim.setdefault(d.dimension, []).append((rec.when, d.score))

    trends: dict[str, DimensionTrend] = {}
    for name, series in by_dim.items():
        series.sort(key=lambda x: x[0])
        scores = [s for _, s in series]
        mean = statistics.fmean(scores)
        latest = scores[-1]
        if len(scores) >= 2:
            prior_mean = statistics.fmean(scores[:-1])
            delta = latest - prior_mean
        else:
            delta = 0.0
        trends[name] = DimensionTrend(
            dimension=name,
            scores=series,
            mean=mean,
            latest=latest,
            delta=delta,
        )
    return trends


def filter_by_persona(records: list[SessionRecord], persona: str | None) -> list[SessionRecord]:
    if persona is None:
        return list(records)
    return [r for r in records if r.persona == persona]


def sparkline(scores: list[int], max_score: int = 5) -> str:
    """ASCII sparkline showing score movement over time."""
    if not scores:
        return ""
    # 8 ticks (U+2581 through U+2588) mapped onto [1, max_score]
    ticks = "▁▂▃▄▅▆▇█"
    lo, hi = 1, max_score
    span = max(1, hi - lo)
    out = []
    for s in scores:
        clamped = max(lo, min(hi, s))
        idx = int(((clamped - lo) / span) * (len(ticks) - 1))
        out.append(ticks[idx])
    return "".join(out)
