"""Shared pytest fixtures + sys.path wiring for agents-team tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `lib/eval/` and `lib/gen/` importable as top-level modules.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib" / "eval"))
sys.path.insert(0, str(PLUGIN_ROOT / "lib" / "gen"))


@pytest.fixture
def write_md(tmp_path: Path):
    """Write Markdown content to a tmp file and return its path."""
    def _write(filename: str, content: str) -> str:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _write


@pytest.fixture
def lint(write_md):
    """Run the static linter on inline content. Returns the report dict."""
    import lint as lint_mod  # type: ignore

    def _run(content: str, *, filename: str = "agent.md", kind: str | None = None,
             strict: bool = False) -> dict:
        path = write_md(filename, content)
        return lint_mod.lint_file(path, kind=kind, strict=strict)
    return _run


@pytest.fixture
def rule_ids():
    """Helper: pull the set of rule IDs out of a report."""
    def _ids(report: dict) -> set[str]:
        return {f["rule"] for f in report["findings"]}
    return _ids
