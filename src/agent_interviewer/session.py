"""Run an interview turn — call Claude as the chosen persona."""

from __future__ import annotations

import anthropic

from agent_interviewer.config import Settings
from agent_interviewer.models import Session, Turn
from agent_interviewer.personas import Persona


def interviewer_reply(
    persona: Persona,
    session: Session,
    settings: Settings,
    *,
    client: anthropic.Anthropic | None = None,
) -> str:
    """Generate the interviewer's next turn based on the session so far.

    The system prompt is cached with cache_control=ephemeral so repeated turns
    inside the same session reuse the prefix.
    """
    if client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
            )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    history = session.to_claude_history()
    if not history or history[0]["role"] != "user":
        # Kick things off with a sentinel user turn so Claude can open the interview.
        history = [{"role": "user", "content": "Let's begin the interview."}] + history

    response = client.messages.create(
        model=settings.interviewer_model,
        max_tokens=500,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": persona.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=history,
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    return text


def append_turn(session: Session, role: str, text: str) -> Turn:
    if role not in {"interviewer", "candidate"}:
        raise ValueError(f"Bad role: {role}")
    turn = Turn(role=role, text=text)  # type: ignore[arg-type]
    session.turns.append(turn)
    return turn
