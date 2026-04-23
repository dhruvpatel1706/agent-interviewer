"""Persist sessions as JSONL under `sessions_dir`."""

from __future__ import annotations

import json
from pathlib import Path

from agent_interviewer.models import Session, Turn


def session_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.jsonl"


def meta_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.meta.json"


def save_turn(sessions_dir: Path, session_id: str, turn: Turn) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    with session_path(sessions_dir, session_id).open("a", encoding="utf-8") as f:
        f.write(turn.model_dump_json() + "\n")


def save_meta(sessions_dir: Path, session_id: str, persona: str) -> None:
    """Write the small sidecar recording which persona this session used.

    Safe to call on every turn — writes are idempotent. Needed so `progress`
    can group scores by persona across sessions without guessing.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    meta_path(sessions_dir, session_id).write_text(
        json.dumps({"persona": persona}), encoding="utf-8"
    )


def read_meta(sessions_dir: Path, session_id: str) -> dict | None:
    p = meta_path(sessions_dir, session_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_session(sessions_dir: Path, session_id: str, persona: str) -> Session:
    """Reconstruct a session from its JSONL file (used when resuming).

    `persona` is a fallback — if a `.meta.json` sidecar exists, its persona
    wins (which is what you want for `progress`, where the caller can't
    reliably know which persona ran which old session).
    """
    turns: list[Turn] = []
    p = session_path(sessions_dir, session_id)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                turns.append(Turn.model_validate_json(line))

    meta = read_meta(sessions_dir, session_id) or {}
    actual_persona = meta.get("persona") or persona
    return Session(id=session_id, persona=actual_persona, turns=turns)


def write_feedback(sessions_dir: Path, session_id: str, feedback_json: str) -> Path:
    """Save feedback as a sidecar `.feedback.json` next to the session's JSONL."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    out = sessions_dir / f"{session_id}.feedback.json"
    out.write_text(feedback_json, encoding="utf-8")
    return out
