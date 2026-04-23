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


def write_feedback(
    sessions_dir: Path,
    session_id: str,
    feedback_json: str,
    *,
    variant: str | None = None,
) -> Path:
    """Save feedback as a sidecar next to the session's JSONL.

    With no `variant`, writes `<session_id>.feedback.json` (the default the
    interview loop uses). With a `variant` (e.g. a model slug like
    `claude-sonnet-4-6`), writes `<session_id>.feedback.<variant>.json` so
    the original feedback isn't overwritten. Useful for replaying a
    transcript through a different evaluator.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    if variant:
        safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in variant)
        out = sessions_dir / f"{session_id}.feedback.{safe}.json"
    else:
        out = sessions_dir / f"{session_id}.feedback.json"
    out.write_text(feedback_json, encoding="utf-8")
    return out


def list_feedback_variants(sessions_dir: Path, session_id: str) -> list[str]:
    """Return every variant label we have saved for a session.

    Empty string represents the default (unlabeled) feedback file.
    """
    out: list[str] = []
    if (sessions_dir / f"{session_id}.feedback.json").exists():
        out.append("")
    prefix = f"{session_id}.feedback."
    for p in sessions_dir.glob(f"{session_id}.feedback.*.json"):
        name = p.name
        label = name[len(prefix) : -len(".json")]
        if label:
            out.append(label)
    return sorted(out)
