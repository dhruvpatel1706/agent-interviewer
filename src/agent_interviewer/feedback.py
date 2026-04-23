"""Post-session feedback: synthesize per-dimension scores from the transcript."""

from __future__ import annotations

import anthropic

from agent_interviewer.config import Settings
from agent_interviewer.models import Feedback, Session
from agent_interviewer.personas import Persona

SYSTEM_PROMPT = """You are a calibrated interview assessor. Given an interview transcript \
and a set of evaluation dimensions, produce a structured feedback report.

Rules:
- Score each provided dimension on 1-5 (5 = ready-to-hire signal). Be honest and specific; \
do not inflate scores.
- Ground every observation in a quotable moment from the transcript. Never fabricate evidence.
- Strengths and growth areas must reference specific moments, not generalities.
- If the transcript is too short to assess a dimension, say so in `observation` and score 2-3.
- `mock_recommendation` reflects what you'd advise if this were the real interview at a strong bar.
"""


def generate_feedback(
    persona: Persona,
    session: Session,
    settings: Settings,
    *,
    client: anthropic.Anthropic | None = None,
) -> Feedback:
    if client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
            )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    if not session.turns:
        raise ValueError("Cannot generate feedback for an empty session.")

    transcript_lines = []
    for turn in session.turns:
        speaker = "INTERVIEWER" if turn.role == "interviewer" else "CANDIDATE"
        transcript_lines.append(f"{speaker}: {turn.text}")
    transcript = "\n\n".join(transcript_lines)

    user_prompt = (
        f"Interview type: {persona.display_name}\n"
        f"Evaluation dimensions (score each): {', '.join(persona.dimensions)}\n\n"
        f"Transcript:\n\n{transcript}"
    )

    response = client.messages.parse(
        model=settings.feedback_model,
        max_tokens=2500,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
        output_format=Feedback,
    )
    if response.parsed_output is None:
        raise RuntimeError(f"Feedback parsing failed. stop_reason={response.stop_reason}")
    return response.parsed_output
