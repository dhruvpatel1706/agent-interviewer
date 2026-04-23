"""Persist sessions as JSONL under `sessions_dir`."""

from __future__ import annotations

from pathlib import Path

from agent_interviewer.models import Session, Turn


def session_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.jsonl"


def save_turn(sessions_dir: Path, session_id: str, turn: Turn) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    with session_path(sessions_dir, session_id).open("a", encoding="utf-8") as f:
        f.write(turn.model_dump_json() + "\n")


def load_session(sessions_dir: Path, session_id: str, persona: str) -> Session:
    """Reconstruct a session from its JSONL file (used when resuming)."""
    turns: list[Turn] = []
    p = session_path(sessions_dir, session_id)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                turns.append(Turn.model_validate_json(line))
    return Session(id=session_id, persona=persona, turns=turns)


def write_feedback(sessions_dir: Path, session_id: str, feedback_json: str) -> Path:
    """Save feedback as a sidecar `.feedback.json` next to the session's JSONL."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    out = sessions_dir / f"{session_id}.feedback.json"
    out.write_text(feedback_json, encoding="utf-8")
    return out
