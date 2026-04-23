"""Small read-only web UI for browsing past interview sessions.

Interviews themselves stay in the CLI — running an interview in a browser
needs a real websocket chat layer, and that's more UI plumbing than this
project is worth. What the UI does cover: flipping through past sessions,
reading transcripts, comparing feedback variants side-by-side, and a
progress page that mirrors the `progress` subcommand.

No template engine, no JS framework. Server-rendered HTML with a thin
stylesheet and `html.escape` on every user-controlled string.
"""

from __future__ import annotations

import html
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from agent_interviewer.config import get_settings
from agent_interviewer.models import Feedback
from agent_interviewer.progress import dimension_trends, load_records, sparkline
from agent_interviewer.storage import (
    list_feedback_variants,
    load_session,
    meta_path,
)

router = APIRouter()

PAGE_CSS = """
  :root { color-scheme: light dark; }
  body { font: 14px/1.5 -apple-system, system-ui, sans-serif; max-width: 960px;
         margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.3rem; margin: 0 0 .5rem; }
  h2 { font-size: 1.1rem; margin: 1.5rem 0 .5rem; }
  nav { margin-bottom: 1.5rem; border-bottom: 1px solid #ddd; padding-bottom: .5rem; }
  nav a { margin-right: 1rem; text-decoration: none; color: #0070c9; }
  table { border-collapse: collapse; width: 100%; margin: .5rem 0; font-size: 13px; }
  th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #e4e4e4;
           vertical-align: top; }
  th { background: #f3f3f3; font-weight: 600; }
  .score-bar { font-family: ui-monospace, monospace; color: #b58900; }
  .dim { color: #666; }
  .transcript { white-space: pre-wrap; background: #f9f9f9; padding: .75rem 1rem;
                border-radius: 4px; border-left: 3px solid #3b82f6; }
  .candidate { color: #444; }
  .interviewer { color: #0b6a2e; }
  .label { font-weight: 600; margin-right: .5rem; }
  @media (prefers-color-scheme: dark) {
    body { background: #111; color: #eee; }
    nav { border-color: #333; }
    nav a { color: #60a5fa; }
    th { background: #1a1a1a; }
    th, td { border-bottom-color: #333; }
    .transcript { background: #1a1a1a; border-left-color: #60a5fa; }
    .candidate { color: #ddd; }
    .interviewer { color: #6fe89a; }
    .dim { color: #888; }
  }
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style></head>
<body>
<nav>
  <a href="/ui">Sessions</a>
  <a href="/ui/progress">Progress</a>
</nav>
{body}
</body></html>""")


def _list_sessions(sessions_dir) -> list[dict]:  # type: ignore[no-untyped-def]
    if not sessions_dir.exists():
        return []
    out: list[dict] = []
    for p in sorted(sessions_dir.glob("*.jsonl"), reverse=True):
        session_id = p.stem
        meta_file = meta_path(sessions_dir, session_id)
        persona = None
        if meta_file.is_file():
            try:
                persona = json.loads(meta_file.read_text()).get("persona")
            except json.JSONDecodeError:
                persona = None
        variants = list_feedback_variants(sessions_dir, session_id)
        out.append({"id": session_id, "persona": persona or "?", "variants": variants})
    return out


@router.get("/ui", response_class=HTMLResponse)
def ui_home() -> HTMLResponse:
    settings = get_settings()
    sessions = _list_sessions(settings.sessions_dir)
    if not sessions:
        body = "<h1>No sessions yet</h1><p class='dim'>Run <code>agent-interviewer start</code> to record one.</p>"
        return _page("agent-interviewer", body)

    rows = []
    for s in sessions:
        v_label = "original"
        if s["variants"]:
            v_label = ", ".join(v or "original" for v in s["variants"])
        rows.append(
            f"<tr><td><a href='/ui/session/{html.escape(s['id'])}'>{html.escape(s['id'])}</a></td>"
            f"<td>{html.escape(s['persona'])}</td>"
            f"<td class='dim'>{html.escape(v_label)}</td></tr>"
        )
    body = (
        "<h1>Past sessions</h1>"
        "<table><thead><tr><th>id</th><th>persona</th><th>feedback variants</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return _page("agent-interviewer — sessions", body)


@router.get("/ui/session/{session_id}", response_class=HTMLResponse)
def ui_session(session_id: str) -> HTMLResponse:
    settings = get_settings()
    session = load_session(settings.sessions_dir, session_id, persona="behavioral")
    if not session.turns:
        return _page("not found", f"<h1>Session {html.escape(session_id)} not found</h1>")

    # Transcript
    lines = []
    for t in session.turns:
        cls = "interviewer" if t.role == "interviewer" else "candidate"
        lines.append(
            f"<div class='{cls}'><span class='label'>{html.escape(t.role)}:</span>"
            f"{html.escape(t.text)}</div>"
        )
    transcript_html = f"<div class='transcript'>{''.join(lines)}</div>"

    # Feedback variants (every .feedback.*.json we can find)
    variants = list_feedback_variants(settings.sessions_dir, session_id)
    feedback_sections = []
    for v in variants:
        if v == "":
            label = "original"
            file = settings.sessions_dir / f"{session_id}.feedback.json"
        else:
            label = v
            file = settings.sessions_dir / f"{session_id}.feedback.{v}.json"
        try:
            fb = Feedback.model_validate_json(file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        dim_rows = []
        for d in fb.dimensions:
            bar = "█" * d.score + "░" * (5 - d.score)
            dim_rows.append(
                f"<tr><td>{html.escape(d.dimension)}</td>"
                f"<td class='score-bar'>{bar}</td>"
                f"<td>{d.score}/5</td>"
                f"<td>{html.escape(d.observation)}</td></tr>"
            )
        feedback_sections.append(
            f"<h2>Feedback — {html.escape(label)}</h2>"
            f"<p>{html.escape(fb.overall)}</p>"
            "<table><thead><tr><th>dimension</th><th></th>"
            "<th>score</th><th>observation</th></tr></thead>"
            f"<tbody>{''.join(dim_rows)}</tbody></table>"
            f"<p class='dim'>Recommendation: {html.escape(fb.mock_recommendation)}</p>"
        )

    body = (
        f"<h1>{html.escape(session_id)} <span class='dim'>· {html.escape(session.persona)}</span></h1>"
        "<h2>Transcript</h2>" + transcript_html + "".join(feedback_sections)
    )
    return _page(f"session {session_id}", body)


@router.get("/ui/progress", response_class=HTMLResponse)
def ui_progress() -> HTMLResponse:
    settings = get_settings()
    records = load_records(settings.sessions_dir)
    if not records:
        return _page("progress", "<h1>No completed sessions with feedback yet.</h1>")

    # Group by persona — different rubrics, don't average across
    by_persona: dict[str, list] = {}
    for rec in records:
        by_persona.setdefault(rec.persona, []).append(rec)

    sections = []
    for persona, rec_list in sorted(by_persona.items()):
        trends = dimension_trends(rec_list)
        rows = []
        for name in sorted(trends):
            t = trends[name]
            spark = sparkline([s for _, s in t.scores])
            arrow = "→"
            if t.delta > 0.3:
                arrow = "↑"
            elif t.delta < -0.3:
                arrow = "↓"
            rows.append(
                f"<tr><td>{html.escape(name)}</td>"
                f"<td class='score-bar'>{html.escape(spark)}</td>"
                f"<td>{t.latest}/5</td>"
                f"<td>{t.mean:.1f}</td>"
                f"<td>{arrow} {t.delta:+.1f}</td></tr>"
            )
        sections.append(
            f"<h2>{html.escape(persona)} <span class='dim'>"
            f"({len(rec_list)} session(s))</span></h2>"
            "<table><thead><tr><th>dimension</th><th>trend</th>"
            "<th>latest</th><th>mean</th><th>Δ vs prior</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    return _page("progress", "<h1>Progress</h1>" + "".join(sections))
