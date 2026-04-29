"""Snapshot test for the Markdown renderer (lib/eval/render.sh).

Reads a known JSON report, runs render.sh, and asserts the produced
Markdown contains the expected key blocks. We do not snapshot the full
text so cosmetic-only changes don't churn the test.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RENDER_SH = PLUGIN_ROOT / "lib" / "eval" / "render.sh"
SAMPLE = PLUGIN_ROOT / "lib" / "eval" / "fixtures" / "sample-report.json"


pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None,
    reason="render.sh requires jq",
)


def run_render(arg: str) -> str:
    r = subprocess.run(
        ["bash", str(RENDER_SH), arg],
        capture_output=True, text=True, check=True,
    )
    return r.stdout


def test_render_emits_verdict_line():
    out = run_render(str(SAMPLE))
    assert "**Verdict: ship**" in out
    assert "Grade B (78/100)" in out


def test_render_emits_dimension_table():
    out = run_render(str(SAMPLE))
    # Header
    assert "| Dimension" in out
    # All 6 dimensions present
    for dim in ("frontmatter", "description", "tool_hygiene",
                "model_fit", "body_structure", "anti_patterns"):
        assert dim in out


def test_render_groups_findings_by_severity():
    out = run_render(str(SAMPLE))
    # The sample has 1 critical, 1 warning, 1 suggestion.
    assert "## Critical findings" in out
    assert "## Warnings" in out
    assert "## Suggestions" in out


def test_render_includes_source_url():
    out = run_render(str(SAMPLE))
    assert "https://code.claude.com/docs/en/sub-agents" in out


def test_render_includes_summary_oneliner():
    out = run_render(str(SAMPLE))
    assert "code-reviewer: B (78/100)" in out
    assert "1 critical" in out


def test_render_via_stdin_dash():
    json_text = SAMPLE.read_text(encoding="utf-8")
    r = subprocess.run(
        ["bash", str(RENDER_SH), "-"],
        input=json_text, capture_output=True, text=True, check=True,
    )
    assert "**Verdict: ship**" in r.stdout
