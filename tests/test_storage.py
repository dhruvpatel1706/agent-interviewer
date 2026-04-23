"""Tests for session persistence."""

from __future__ import annotations

from agent_interviewer.models import Session, Turn
from agent_interviewer.storage import load_session, save_turn


def test_save_and_reload_turns(tmp_path) -> None:
    session_id = "abcd1234"
    sessions_dir = tmp_path / "sessions"

    save_turn(sessions_dir, session_id, Turn(role="interviewer", text="Hello."))
    save_turn(sessions_dir, session_id, Turn(role="candidate", text="Hi there."))
    save_turn(sessions_dir, session_id, Turn(role="interviewer", text="Tell me about yourself."))

    reloaded = load_session(sessions_dir, session_id, persona="behavioral")
    assert len(reloaded.turns) == 3
    assert [t.role for t in reloaded.turns] == ["interviewer", "candidate", "interviewer"]
    assert reloaded.turns[1].text == "Hi there."


def test_load_missing_session_returns_empty(tmp_path) -> None:
    session = load_session(tmp_path, "nonexistent", persona="behavioral")
    assert session.turns == []


def test_session_to_claude_history() -> None:
    session = Session(id="x", persona="behavioral")
    session.turns = [
        Turn(role="interviewer", text="Hello"),
        Turn(role="candidate", text="Hi"),
        Turn(role="interviewer", text="Tell me more"),
    ]
    history = session.to_claude_history()
    assert history == [
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Tell me more"},
    ]
