"""FastAPI app hosting only the /ui viewer (v0.5).

Deliberately no interactive interview endpoints — the CLI already does that
better than a browser would without a proper websocket chat layer, and
agents-as-a-web-app is an entire other project.
"""

from __future__ import annotations

from fastapi import FastAPI

from agent_interviewer import __version__
from agent_interviewer.web import router as ui_router

app = FastAPI(
    title="agent-interviewer",
    version=__version__,
    description="Browse past interview sessions and feedback (read-only).",
)
app.include_router(ui_router)
