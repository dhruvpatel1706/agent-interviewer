"""Tests for the read-only web viewer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent_interviewer.models import DimensionScore, Feedback, Turn
from agent_interviewer.server import app
from agent_interviewer.storage import save_meta, save_turn, write_feedback


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the app at a throwaway sessions dir.
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path))
    # Our Settings uses env prefix via pydantic-settings, but in case it's
    # cached we also patch get_settings directly.
    from agent_interviewer import config as cfg

    class _Scoped:
        anthropic_api_key = ""
        interviewer_model = "claude-opus-4-7"
        feedback_model = "claude-opus-4-7"
        sessions_dir = tmp_path

    monkeypatch.setattr(cfg, "get_settings", lambda: _Scoped)  # type: ignore[assignment]
    monkeypatch.setattr("agent_interviewer.web.get_settings", lambda: _Scoped)
    return TestClient(app)


def _feedback(scores: dict[str, int]) -> Feedback:
    return Feedback(
        overall="ok overall",
        dimensions=[
            DimensionScore(dimension=k, score=v, observation="ob", suggestion="sug")
            for k, v in scores.items()
        ],
        strengths=["s1"],
        growth_areas=["g1"],
        mock_recommendation="borderline",
    )


def _seed(sessions_dir, session_id: str, persona: str):
    when = datetime(2026, 4, 1, tzinfo=timezone.utc)
    save_turn(
        sessions_dir,
        session_id,
        Turn(role="interviewer", text="Tell me about yourself.", timestamp=when),
    )
    save_turn(
        sessions_dir,
        session_id,
        Turn(role="candidate", text="I build open-source tools.", timestamp=when),
    )
    save_meta(sessions_dir, session_id, persona)


def test_home_empty(client, tmp_path):
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "No sessions yet" in resp.text


def test_home_lists_sessions(client, tmp_path):
    _seed(tmp_path, "abc123", "coding")
    _seed(tmp_path, "def456", "behavioral")
    resp = client.get("/ui")
    assert resp.status_code == 200
    body = resp.text
    assert "abc123" in body
    assert "def456" in body
    assert "coding" in body


def test_session_detail_404(client):
    resp = client.get("/ui/session/does-not-exist")
    assert resp.status_code == 200  # still renders, but says not found
    assert "not found" in resp.text.lower()


def test_session_detail_renders_transcript_and_feedback(client, tmp_path):
    _seed(tmp_path, "abc123", "coding")
    write_feedback(
        tmp_path,
        "abc123",
        _feedback({"correctness": 4}).model_dump_json(),
    )
    resp = client.get("/ui/session/abc123")
    assert resp.status_code == 200
    body = resp.text
    # Transcript content
    assert "Tell me about yourself" in body
    assert "I build open-source tools" in body
    # Feedback
    assert "correctness" in body
    assert "ok overall" in body


def test_session_detail_escapes_xss(client, tmp_path):
    bad = "<script>alert('xss')</script>"
    save_turn(
        tmp_path,
        "xss-test",
        Turn(role="candidate", text=bad, timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc)),
    )
    save_meta(tmp_path, "xss-test", "coding")
    resp = client.get("/ui/session/xss-test")
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_session_detail_shows_compare_link_with_two_variants(client, tmp_path):
    _seed(tmp_path, "two-variants", "coding")
    write_feedback(tmp_path, "two-variants", _feedback({"x": 3}).model_dump_json())
    write_feedback(
        tmp_path, "two-variants", _feedback({"x": 4}).model_dump_json(), variant="sonnet"
    )
    resp = client.get("/ui/session/two-variants")
    assert resp.status_code == 200
    assert "compare variants" in resp.text
    assert "/compare?a=" in resp.text


def test_session_detail_no_compare_link_with_one_variant(client, tmp_path):
    _seed(tmp_path, "one-variant", "coding")
    write_feedback(tmp_path, "one-variant", _feedback({"x": 3}).model_dump_json())
    resp = client.get("/ui/session/one-variant")
    assert "compare variants" not in resp.text


def test_compare_deltas_match(client, tmp_path):
    _seed(tmp_path, "cmp-1", "coding")
    write_feedback(
        tmp_path,
        "cmp-1",
        _feedback({"clarity": 3, "correctness": 4}).model_dump_json(),
    )
    write_feedback(
        tmp_path,
        "cmp-1",
        _feedback({"clarity": 5, "correctness": 4}).model_dump_json(),
        variant="sonnet",
    )
    resp = client.get("/ui/session/cmp-1/compare?a=original&b=sonnet")
    assert resp.status_code == 200
    body = resp.text
    # Delta for clarity = 5 - 3 = +2, rendered in delta-up span
    assert "+2" in body
    assert "delta-up" in body
    # Correctness unchanged → a 0 in the delta-zero class
    assert "delta-zero" in body
    # Both variants' observations visible side-by-side
    assert body.count("ob") >= 2


def test_compare_highlights_recommendation_mismatch(client, tmp_path):
    _seed(tmp_path, "cmp-rec", "coding")

    def _fb(rec, score):
        return Feedback(
            overall="o",
            dimensions=[
                DimensionScore(dimension="x", score=score, observation="ob", suggestion="s")
            ],
            strengths=["s1"],
            growth_areas=["g1"],
            mock_recommendation=rec,
        )

    write_feedback(tmp_path, "cmp-rec", _fb("needs-more-prep", 2).model_dump_json())
    write_feedback(
        tmp_path,
        "cmp-rec",
        _fb("ready-to-interview", 4).model_dump_json(),
        variant="haiku",
    )
    resp = client.get("/ui/session/cmp-rec/compare?a=original&b=haiku")
    body = resp.text
    # Both recommendations rendered, and mismatch class applied to both
    assert "needs-more-prep" in body
    assert "ready-to-interview" in body
    assert "mismatch" in body


def test_compare_missing_variant_returns_readable_error(client, tmp_path):
    _seed(tmp_path, "cmp-missing", "coding")
    write_feedback(tmp_path, "cmp-missing", _feedback({"x": 3}).model_dump_json())
    resp = client.get("/ui/session/cmp-missing/compare?a=original&b=nope")
    assert resp.status_code == 200
    assert "not found" in resp.text.lower()


def test_compare_defaults_b_to_other_variant(client, tmp_path):
    _seed(tmp_path, "cmp-default", "coding")
    write_feedback(tmp_path, "cmp-default", _feedback({"x": 3}).model_dump_json())
    write_feedback(tmp_path, "cmp-default", _feedback({"x": 4}).model_dump_json(), variant="haiku")
    # Only `a` provided; `b` should auto-pick the only other variant.
    resp = client.get("/ui/session/cmp-default/compare?a=original")
    assert resp.status_code == 200
    assert "haiku" in resp.text


def test_progress_page_empty(client):
    resp = client.get("/ui/progress")
    assert resp.status_code == 200
    assert "No completed sessions" in resp.text


def test_progress_page_with_data(client, tmp_path):
    # One session + feedback so load_records + dimension_trends have something
    _seed(tmp_path, "prog-1", "coding")
    write_feedback(tmp_path, "prog-1", _feedback({"correctness": 4}).model_dump_json())
    resp = client.get("/ui/progress")
    assert resp.status_code == 200
    body = resp.text
    assert "coding" in body
    assert "correctness" in body
