"""Tests for the YAML persona pack loader."""

from __future__ import annotations

import pytest

from agent_interviewer.pack_loader import load_and_register_default, load_pack, register_pack
from agent_interviewer.personas import PERSONAS


@pytest.fixture(autouse=True)
def _reset_registry():
    """Restore PERSONAS to its original 4 built-in keys after each test."""
    original = dict(PERSONAS)
    yield
    PERSONAS.clear()
    PERSONAS.update(original)


def _write_pack(tmp_path, text: str):
    p = tmp_path / "pack.yml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_minimal_valid_pack(tmp_path):
    p = _write_pack(
        tmp_path,
        """
personas:
  - key: ml-behavioral
    display_name: ML behavioral
    system_prompt: You are an ML research manager. Do not grade during the interview.
    dimensions:
      - taste
      - rigor
      - collaboration
""".strip(),
    )
    personas = load_pack(p)
    assert len(personas) == 1
    persona = personas[0]
    assert persona.key == "ml-behavioral"
    assert persona.dimensions == ("taste", "rigor", "collaboration")


def test_load_rejects_top_level_not_mapping(tmp_path):
    p = _write_pack(tmp_path, "- just a list\n- at top level")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_pack(p)


def test_load_rejects_missing_fields(tmp_path):
    p = _write_pack(
        tmp_path,
        """
personas:
  - key: x
    display_name: X
    # system_prompt missing
    dimensions: [a, b]
""".strip(),
    )
    with pytest.raises(ValueError, match="missing required field"):
        load_pack(p)


def test_load_rejects_duplicate_key_in_pack(tmp_path):
    p = _write_pack(
        tmp_path,
        """
personas:
  - key: dup
    display_name: First
    system_prompt: "first prompt — do not grade"
    dimensions: [a, b, c]
  - key: dup
    display_name: Second
    system_prompt: "second prompt — do not grade"
    dimensions: [a, b, c]
""".strip(),
    )
    with pytest.raises(ValueError, match="duplicate persona key"):
        load_pack(p)


def test_load_rejects_empty_dimensions(tmp_path):
    p = _write_pack(
        tmp_path,
        """
personas:
  - key: x
    display_name: X
    system_prompt: "prompt — do not grade"
    dimensions: []
""".strip(),
    )
    with pytest.raises(ValueError, match="non-empty list"):
        load_pack(p)


def test_register_rejects_collision_with_builtin(tmp_path):
    p = _write_pack(
        tmp_path,
        """
personas:
  - key: coding
    display_name: Custom coding
    system_prompt: hijack
    dimensions: [a, b, c]
""".strip(),
    )
    with pytest.raises(ValueError, match="already exists"):
        register_pack(load_pack(p))


def test_register_merges_into_global_registry(tmp_path):
    p = _write_pack(
        tmp_path,
        """
personas:
  - key: custom-1
    display_name: Custom One
    system_prompt: "prompt one — do not grade"
    dimensions: [a, b, c]
  - key: custom-2
    display_name: Custom Two
    system_prompt: "prompt two — do not grade"
    dimensions: [x, y, z]
""".strip(),
    )
    register_pack(load_pack(p))
    assert "custom-1" in PERSONAS
    assert "custom-2" in PERSONAS


def test_load_and_register_default_missing_explicit_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_and_register_default(explicit=tmp_path / "nope.yml")


def test_load_and_register_default_missing_silent_default(tmp_path, monkeypatch):
    # Default path that doesn't exist -> returns [] without raising
    monkeypatch.setattr("agent_interviewer.pack_loader.DEFAULT_PACK_PATH", tmp_path / "missing.yml")
    assert load_and_register_default(quiet=True) == []
