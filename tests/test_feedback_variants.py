"""Tests for multi-variant feedback persistence."""

from __future__ import annotations

from pathlib import Path

from agent_interviewer.storage import list_feedback_variants, write_feedback


def test_default_variant_writes_unlabeled_file(tmp_path):
    path = write_feedback(tmp_path, "sid", '{"x":1}')
    assert path == tmp_path / "sid.feedback.json"
    assert path.is_file()


def test_named_variant_writes_suffixed_file(tmp_path):
    path = write_feedback(tmp_path, "sid", '{"x":1}', variant="claude-sonnet-4-6")
    assert path == tmp_path / "sid.feedback.claude-sonnet-4-6.json"
    assert path.is_file()


def test_variant_sanitizes_unsafe_chars(tmp_path):
    # Forward slashes and spaces become underscores — no path traversal.
    path = write_feedback(tmp_path, "sid", "{}", variant="some/model with space")
    # ensure the written path is still under tmp_path and uses underscores
    assert path.parent == tmp_path
    assert "/" not in path.name.split("sid.feedback.")[1]


def test_list_variants_empty_when_no_files(tmp_path):
    assert list_feedback_variants(tmp_path, "missing") == []


def test_list_variants_returns_all_present(tmp_path):
    write_feedback(tmp_path, "sid", "{}")  # default
    write_feedback(tmp_path, "sid", "{}", variant="claude-opus-4-7")
    write_feedback(tmp_path, "sid", "{}", variant="claude-sonnet-4-6")
    out = list_feedback_variants(tmp_path, "sid")
    assert "" in out  # unlabeled
    assert "claude-opus-4-7" in out
    assert "claude-sonnet-4-6" in out


def test_list_variants_ignores_other_sessions(tmp_path):
    write_feedback(tmp_path, "sid-a", "{}", variant="x")
    write_feedback(tmp_path, "sid-b", "{}", variant="y")
    assert list_feedback_variants(tmp_path, "sid-a") == ["x"]
