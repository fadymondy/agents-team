"""Tests for the /team-gen self-eval gate (issue #22).

Covers:
  - --no-self-eval without AGENTS_TEAM_DEV=1 → exit 64
  - --no-self-eval with AGENTS_TEAM_DEV=1   → exit 0
  - --min-grade=A on the example team       → exit 0 (everything is A)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = PLUGIN_ROOT / "lib" / "gen" / "scaffold.py"
EXAMPLE_TEAM = PLUGIN_ROOT.parent.parent / "examples" / "example-team.json"


pytestmark = pytest.mark.slow


@pytest.fixture
def target(tmp_path):
    return tmp_path / "team-out"


def _scaffold(target_path: Path, *flags: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    target_path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCAFFOLD), str(EXAMPLE_TEAM), "--target", str(target_path), *flags],
        capture_output=True, text=True, check=False, env=env,
    )


def test_no_self_eval_without_env_var_exits_64(target):
    r = _scaffold(target, "--no-self-eval")
    assert r.returncode == 64, r.stderr
    assert "AGENTS_TEAM_DEV=1" in r.stderr


def test_no_self_eval_with_env_var_exits_zero(target):
    r = _scaffold(target, "--no-self-eval", env_extra={"AGENTS_TEAM_DEV": "1"})
    assert r.returncode == 0, r.stderr


def test_default_min_grade_passes_on_example_team(target):
    r = _scaffold(target)
    assert r.returncode == 0, r.stderr
    assert "min-grade=B" in r.stdout


def test_min_grade_A_passes_on_example_team(target):
    """Every fixture in the example team scores A, so --min-grade A still passes."""
    r = _scaffold(target, "--min-grade", "A")
    assert r.returncode == 0, r.stderr
    assert "min-grade=A" in r.stdout
