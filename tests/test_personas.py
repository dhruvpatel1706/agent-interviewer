"""Tests for persona registry."""

from __future__ import annotations

import pytest

from agent_interviewer.personas import PERSONAS, get_persona


def test_registry_has_four_personas() -> None:
    assert set(PERSONAS) == {"behavioral", "system-design", "coding", "case"}


def test_every_persona_has_dimensions_and_prompt() -> None:
    # Every persona prompt should (a) name a role, (b) instruct the model not to
    # grade during the interview, and (c) list at least 3 evaluation dimensions.
    role_markers = ("interviewer", "engineer", "manager")
    no_grading_markers = ("do not grade", "do not give feedback", "not to grade")
    for p in PERSONAS.values():
        prompt_lc = p.system_prompt.lower()
        assert p.display_name
        assert len(p.dimensions) >= 3
        assert any(m in prompt_lc for m in role_markers), f"{p.key} missing role marker"
        assert any(m in prompt_lc for m in no_grading_markers), f"{p.key} missing no-grading clause"


def test_get_persona_by_key() -> None:
    assert get_persona("coding").key == "coding"


def test_get_persona_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_persona("not-a-real-persona")
