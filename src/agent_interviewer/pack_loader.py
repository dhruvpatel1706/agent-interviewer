"""Load user-defined personas from a YAML pack file.

The four built-in personas (behavioral, system-design, coding, case) stay where
they are — this just adds the ability to register more without editing the
source. Good for: role-specific prompts (ML research scientist behavioral,
principal SRE on-call scenarios), interview styles you want to A/B.

Pack format:

    personas:
      - key: ml-research-behavioral
        display_name: ML Research Scientist Behavioral
        system_prompt: |
          You are a research manager at a top ML lab. Probe for...
        dimensions:
          - research taste
          - experimental rigor
          - collaboration
          - publication record
          - independent direction

`key` has to be unique across built-in + user packs; a collision raises so
you don't accidentally silently override the bundled `coding` prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from agent_interviewer.personas import PERSONAS, Persona

DEFAULT_PACK_PATH = Path(
    os.environ.get(
        "AGENT_INTERVIEWER_PACK",
        Path.home() / ".agent-interviewer" / "personas.yml",
    )
)


def load_pack(path: Path) -> list[Persona]:
    """Parse a YAML pack. Does NOT register the personas — caller controls that."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    items = data.get("personas", [])
    if not isinstance(items, list):
        raise ValueError(f"{path}: `personas` must be a list")

    out: list[Persona] = []
    seen: set[str] = set()
    for i, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: personas[{i}] is not a mapping")
        try:
            key = str(raw["key"]).strip()
            display_name = str(raw["display_name"]).strip()
            system_prompt = str(raw["system_prompt"]).strip()
            dimensions_raw = raw["dimensions"]
        except KeyError as exc:
            raise ValueError(f"{path}: personas[{i}] missing required field {exc}") from exc

        if not isinstance(dimensions_raw, list) or not dimensions_raw:
            raise ValueError(f"{path}: personas[{i}].dimensions must be a non-empty list")
        dimensions = tuple(str(d).strip() for d in dimensions_raw)

        if not key or not display_name or not system_prompt:
            raise ValueError(f"{path}: personas[{i}] has empty required fields")
        if key in seen:
            raise ValueError(f"{path}: duplicate persona key {key!r} in pack")
        seen.add(key)

        out.append(
            Persona(
                key=key,
                display_name=display_name,
                dimensions=dimensions,
                system_prompt=system_prompt,
            )
        )
    return out


def register_pack(personas: list[Persona]) -> None:
    """Add user personas into the global PERSONAS registry.

    Raises if any key collides with an already-registered persona. This is a
    deliberate footgun-guard — we'd rather you pick a different `key` than
    have `start --type coding` silently do something surprising.
    """
    for p in personas:
        if p.key in PERSONAS:
            raise ValueError(
                f"Persona key {p.key!r} already exists in the registry "
                "(built-in or previously-loaded pack). Pick a unique key."
            )
    for p in personas:
        PERSONAS[p.key] = p


def load_and_register_default(
    *,
    explicit: Path | None = None,
    quiet: bool = False,
) -> list[Persona]:
    """Best-effort: load `explicit` if given, else DEFAULT_PACK_PATH if present.

    Returns the registered personas (possibly empty). Invalid packs raise;
    a missing default pack is silently tolerated.
    """
    pack_path = explicit or DEFAULT_PACK_PATH
    if not pack_path.is_file():
        if explicit is not None:
            raise FileNotFoundError(f"Pack file not found: {explicit}")
        return []
    personas = load_pack(pack_path)
    register_pack(personas)
    if not quiet:
        names = ", ".join(p.key for p in personas)
        print(f"[personas] loaded {len(personas)} from {pack_path}: {names}")
    return personas
