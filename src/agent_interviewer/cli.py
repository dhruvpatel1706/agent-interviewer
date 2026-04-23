"""Typer CLI: start / resume / list / feedback."""

from __future__ import annotations

import uuid

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agent_interviewer import __version__
from agent_interviewer.config import get_settings
from agent_interviewer.feedback import generate_feedback
from agent_interviewer.models import Session
from agent_interviewer.personas import PERSONAS, get_persona
from agent_interviewer.session import append_turn, interviewer_reply
from agent_interviewer.storage import load_session, save_meta, save_turn, write_feedback

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Multi-persona mock interview CLI backed by Claude.",
)
console = Console()
err = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"agent-interviewer {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    return


@app.command("personas")
def personas_cmd(
    pack: str = typer.Option(
        None,
        "--pack",
        "-p",
        help="Load a custom YAML pack before listing. Default: $AGENT_INTERVIEWER_PACK or ~/.agent-interviewer/personas.yml.",
    ),
) -> None:
    """List available interviewer personas (built-in + loaded from a pack)."""
    _maybe_load_pack(pack)
    table = Table(show_header=True, header_style="bold cyan", title="Interviewer personas")
    table.add_column("key")
    table.add_column("name")
    table.add_column("evaluation dimensions")
    for p in PERSONAS.values():
        table.add_row(p.key, p.display_name, ", ".join(p.dimensions))
    console.print(table)


def _maybe_load_pack(pack_path_str: str | None) -> None:
    """Load the YAML pack (explicit or default location) if present."""
    from agent_interviewer.pack_loader import load_and_register_default

    explicit = __import__("pathlib").Path(pack_path_str) if pack_path_str else None
    try:
        load_and_register_default(explicit=explicit, quiet=True)
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        err.print(f"[yellow](ignoring invalid pack: {exc})[/yellow]")


def _run_interview_loop(session: Session, settings) -> None:  # type: ignore[no-untyped-def]
    persona = get_persona(session.persona)
    console.print(
        Panel.fit(
            f"[bold]{persona.display_name}[/bold]\n[dim]Type /end to finish, /save to flush\n"
            f"Session id: {session.id}[/dim]",
            border_style="cyan",
        )
    )

    # Persist the persona-of-record once at session start (v0.2 — lets
    # `progress` group sessions by their persona without guessing).
    save_meta(settings.sessions_dir, session.id, persona.key)

    # If this is a fresh session, open with the interviewer's kickoff.
    if not session.turns:
        with console.status("[cyan]Interviewer is preparing...", spinner="dots"):
            opening = interviewer_reply(persona, session, settings)
        turn = append_turn(session, "interviewer", opening)
        save_turn(settings.sessions_dir, session.id, turn)
        console.print(f"[cyan]Interviewer:[/cyan] {opening}\n")

    while True:
        try:
            reply = Prompt.ask("[yellow]You[/yellow]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim](ended via Ctrl-D)[/dim]")
            break
        if not reply:
            continue
        if reply.lower() == "/end":
            break
        if reply.lower() == "/save":
            console.print("[dim](all turns are saved automatically)[/dim]")
            continue

        turn = append_turn(session, "candidate", reply)
        save_turn(settings.sessions_dir, session.id, turn)

        with console.status("[cyan]Interviewer is thinking...", spinner="dots"):
            reply_text = interviewer_reply(persona, session, settings)
        turn = append_turn(session, "interviewer", reply_text)
        save_turn(settings.sessions_dir, session.id, turn)
        console.print(f"\n[cyan]Interviewer:[/cyan] {reply_text}\n")


@app.command("start")
def start_cmd(
    persona_key: str = typer.Option(
        "behavioral",
        "--type",
        "-t",
        help="Persona key. Run `agent-interviewer personas` to list.",
    ),
    pack: str = typer.Option(None, "--pack", "-p", help="Custom YAML persona pack."),
    no_feedback: bool = typer.Option(
        False, "--no-feedback", help="Skip the post-session feedback agent."
    ),
) -> None:
    """Start a new mock interview."""
    _maybe_load_pack(pack)
    settings = get_settings()
    persona = get_persona(persona_key)
    session = Session(id=uuid.uuid4().hex[:10], persona=persona.key)

    _run_interview_loop(session, settings)

    if not session.turns:
        console.print("[dim]No turns recorded — skipping feedback.[/dim]")
        return
    if no_feedback:
        console.print(
            f"[green]Session saved.[/green] Run `agent-interviewer feedback {session.id}` "
            "when you want the critique."
        )
        return

    _print_feedback_for(session, settings)


@app.command("resume")
def resume_cmd(session_id: str = typer.Argument(...)) -> None:
    """Resume an existing session by id."""
    settings = get_settings()
    # persona is recovered from the stored session's first turn context — fall back to behavioral
    session = load_session(settings.sessions_dir, session_id, persona="behavioral")
    if not session.turns:
        console.print(f"[red]No session found at id {session_id}[/red]")
        raise typer.Exit(1)
    _run_interview_loop(session, settings)
    _print_feedback_for(session, settings)


@app.command("feedback")
def feedback_cmd(session_id: str = typer.Argument(...)) -> None:
    """Generate feedback for a previously-recorded session."""
    settings = get_settings()
    session = load_session(settings.sessions_dir, session_id, persona="behavioral")
    if not session.turns:
        console.print(f"[red]No session found at id {session_id}[/red]")
        raise typer.Exit(1)
    _print_feedback_for(session, settings)


def _print_feedback_for(session: Session, settings) -> None:  # type: ignore[no-untyped-def]
    persona = get_persona(session.persona)
    console.print()
    with console.status("[cyan]Generating feedback...", spinner="dots"):
        fb = generate_feedback(persona, session, settings)
    write_feedback(settings.sessions_dir, session.id, fb.model_dump_json(indent=2))

    console.print(Panel(fb.overall, title="Overall", border_style="cyan"))

    dim_table = Table(show_header=True, header_style="bold cyan", title="Per-dimension scores")
    dim_table.add_column("dimension", no_wrap=True)
    dim_table.add_column("score", justify="right")
    dim_table.add_column("observation")
    dim_table.add_column("suggestion")
    for d in fb.dimensions:
        bar = "█" * d.score + "░" * (5 - d.score)
        dim_table.add_row(
            d.dimension, f"[yellow]{bar}[/yellow] {d.score}/5", d.observation, d.suggestion
        )
    console.print(dim_table)

    console.print("\n[bold green]Strengths:[/bold green]")
    for s in fb.strengths:
        console.print(f"  • {s}")
    console.print("\n[bold red]Growth areas:[/bold red]")
    for g in fb.growth_areas:
        console.print(f"  • {g}")

    color = {"needs-more-prep": "red", "borderline": "yellow", "ready-to-interview": "green"}[
        fb.mock_recommendation
    ]
    console.print(
        f"\n[bold]Mock recommendation:[/bold] [{color}]{fb.mock_recommendation}[/{color}]"
    )


@app.command("progress")
def progress_cmd(
    persona_key: str = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by persona (behavioral, system-design, coding, case). Default: all.",
    ),
) -> None:
    """Show per-dimension score trends across past sessions."""
    from agent_interviewer.progress import (
        dimension_trends,
        filter_by_persona,
        load_records,
        sparkline,
    )

    settings = get_settings()
    records = filter_by_persona(load_records(settings.sessions_dir), persona_key)
    if not records:
        msg = (
            "[dim]No sessions with feedback yet.[/dim]"
            if persona_key is None
            else f"[dim]No {persona_key!r} sessions yet.[/dim]"
        )
        console.print(msg)
        return

    # Group by persona when no filter is set, so scores from different rubrics
    # aren't averaged into each other.
    by_persona: dict[str, list] = {}
    for rec in records:
        by_persona.setdefault(rec.persona, []).append(rec)

    for persona_name, persona_records in sorted(by_persona.items()):
        trends = dimension_trends(persona_records)
        console.print(
            f"\n[bold cyan]{persona_name}[/bold cyan]  "
            f"[dim]({len(persona_records)} session(s))[/dim]"
        )
        table = Table(show_header=True, header_style="bold")
        table.add_column("dimension", no_wrap=True)
        table.add_column("trend")
        table.add_column("latest", justify="right")
        table.add_column("mean", justify="right")
        table.add_column("Δ vs prior", justify="right")
        for name in sorted(trends):
            t = trends[name]
            scores_only = [s for _, s in t.scores]
            arrow = "→"
            color = "dim"
            if t.delta > 0.3:
                arrow, color = "↑", "green"
            elif t.delta < -0.3:
                arrow, color = "↓", "red"
            sp = sparkline(scores_only)
            table.add_row(
                name,
                f"[yellow]{sp}[/yellow]",
                f"{t.latest}/5",
                f"{t.mean:.1f}",
                f"[{color}]{arrow} {t.delta:+.1f}[/{color}]",
            )
        console.print(table)


if __name__ == "__main__":
    app()
