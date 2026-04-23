"""Tests for longitudinal progress analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_interviewer.models import DimensionScore, Feedback, Session, Turn
from agent_interviewer.progress import (
    dimension_trends,
    filter_by_persona,
    load_records,
    sparkline,
)


def _fb(scores_by_dim: dict[str, int]) -> Feedback:
    return Feedback(
        overall="ok",
        dimensions=[
            DimensionScore(dimension=d, score=s, observation="x", suggestion="y")
            for d, s in scores_by_dim.items()
        ],
        strengths=["something"],
        growth_areas=["something else"],
        mock_recommendation="borderline",
    )


def _write_pair(sessions_dir: Path, session_id: str, persona: str, when: datetime, fb: Feedback):
    sessions_dir.mkdir(parents=True, exist_ok=True)
    # Transcript with at least one turn so load_records will accept it.
    session = Session(
        id=session_id,
        persona=persona,
        turns=[Turn(role="interviewer", text="hi", timestamp=when)],
    )
    (sessions_dir / f"{session_id}.jsonl").write_text(
        session.turns[0].model_dump_json() + "\n", encoding="utf-8"
    )
    (sessions_dir / f"{session_id}.feedback.json").write_text(
        fb.model_dump_json(), encoding="utf-8"
    )


def test_load_skips_sessions_without_feedback(tmp_path):
    # Only a transcript, no feedback sidecar
    (tmp_path / "sol0a.jsonl").write_text("", encoding="utf-8")
    assert load_records(tmp_path) == []


def test_load_skips_orphan_feedback(tmp_path):
    # feedback exists but no transcript
    (tmp_path / "abc.feedback.json").write_text(_fb({"a": 3}).model_dump_json(), encoding="utf-8")
    assert load_records(tmp_path) == []


def test_load_returns_records_sorted_oldest_first(tmp_path):
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    _write_pair(tmp_path, "aaa", "coding", t2, _fb({"x": 3}))
    _write_pair(tmp_path, "bbb", "coding", t1, _fb({"x": 4}))
    _write_pair(tmp_path, "ccc", "coding", t3, _fb({"x": 5}))
    records = load_records(tmp_path)
    assert [r.session_id for r in records] == ["bbb", "aaa", "ccc"]


def test_filter_by_persona(tmp_path):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_pair(tmp_path, "a", "coding", t, _fb({"x": 3}))
    _write_pair(tmp_path, "b", "behavioral", t + timedelta(days=1), _fb({"x": 4}))
    all_recs = load_records(tmp_path)
    coding = filter_by_persona(all_recs, "coding")
    assert [r.session_id for r in coding] == ["a"]
    assert filter_by_persona(all_recs, None) == all_recs


def test_dimension_trends_positive_delta(tmp_path):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, score in enumerate([2, 3, 4]):
        _write_pair(
            tmp_path,
            f"s{i}",
            "coding",
            base + timedelta(days=i),
            _fb({"correctness": score}),
        )
    trends = dimension_trends(load_records(tmp_path))
    t = trends["correctness"]
    assert t.latest == 4
    assert t.mean == (2 + 3 + 4) / 3
    # Prior-mean was 2.5; latest 4 -> delta +1.5
    assert t.delta == 4 - 2.5


def test_dimension_trends_single_session_has_zero_delta(tmp_path):
    _write_pair(
        tmp_path,
        "only",
        "coding",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        _fb({"correctness": 3}),
    )
    trends = dimension_trends(load_records(tmp_path))
    assert trends["correctness"].delta == 0.0


def test_sparkline_empty_returns_empty():
    assert sparkline([]) == ""


def test_sparkline_all_same_value_is_constant():
    out = sparkline([3, 3, 3, 3])
    assert len(out) == 4
    assert out[0] == out[-1]


def test_sparkline_up_then_down():
    out = sparkline([1, 3, 5, 3, 1])
    # We don't assert exact glyphs — just that it's the right length
    # and the middle character ranks highest.
    assert len(out) == 5
    ranks = "▁▂▃▄▅▆▇█"
    assert ranks.index(out[2]) > ranks.index(out[0])
