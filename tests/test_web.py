"""Tests for the read-only web viewer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent_interviewer.models import DimensionScore, Feedback, Session, Turn
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
