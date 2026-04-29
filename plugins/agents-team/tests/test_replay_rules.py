"""Tests for the new behavioral rules added in #17.

Each test feeds replay.grade() a synthetic transcript and asserts the
expected rule fires (or does NOT fire on a clean transcript).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import replay  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
DOMAIN_ENGINEER_AGENT = """---
name: api-engineer
description: "API engineer for the e-Shop team. Owns services/api/ — REST handlers, validation, DB models. Use proactively after the orchestrator picks an API task."
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# API Engineer

Owns `services/api/`.

## When invoked
1. Read the change.

## Constraints
- Stay in your service.
"""


@pytest.fixture
def agent(tmp_path):
    p = tmp_path / "api-engineer.md"
    p.write_text(DOMAIN_ENGINEER_AGENT, encoding="utf-8")
    return str(p)


def write_transcript(tmp_path: Path, events: list[dict]) -> str:
    p = tmp_path / "transcript.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return str(p)


def rule_ids(report) -> set[str]:
    return {f["rule"] for f in report["findings"]}


# ---------------------------------------------------------------------------
# domain_adherence_violation
# ---------------------------------------------------------------------------
def test_domain_adherence_fires_on_out_of_scope_paths(agent, tmp_path):
    """API engineer reading apps/web/ files should fire the violation."""
    transcript = write_transcript(tmp_path, [
        {"type": "tool_use", "name": "Read",  "input": {"path": "services/api/users.ts"}},
        {"type": "tool_use", "name": "Read",  "input": {"path": "apps/web/checkout.tsx"}},
        {"type": "tool_use", "name": "Read",  "input": {"path": "apps/mobile/lib/cart.dart"}},
        {"type": "tool_use", "name": "Edit",  "input": {"path": "apps/web/cart.tsx"}},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.domain_adherence_violation" in rule_ids(r)


def test_domain_adherence_silent_on_in_scope_paths(agent, tmp_path):
    transcript = write_transcript(tmp_path, [
        {"type": "tool_use", "name": "Read", "input": {"path": "services/api/users.ts"}},
        {"type": "tool_use", "name": "Read", "input": {"path": "services/api/orders.ts"}},
        {"type": "tool_use", "name": "Edit", "input": {"path": "services/api/users.ts"}},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.domain_adherence_violation" not in rule_ids(r)


# ---------------------------------------------------------------------------
# self_correction_failure
# ---------------------------------------------------------------------------
def test_self_correction_failure_on_three_identical_calls(agent, tmp_path):
    same = {"type": "tool_use", "name": "Bash", "input": {"command": "pnpm build"}}
    transcript = write_transcript(tmp_path, [same, same, same])
    r = replay.grade(agent, transcript)
    assert "behavioral.self_correction_failure" in rule_ids(r)


def test_self_correction_silent_on_varied_calls(agent, tmp_path):
    transcript = write_transcript(tmp_path, [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pnpm build"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pnpm lint"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pnpm test"}},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.self_correction_failure" not in rule_ids(r)


# ---------------------------------------------------------------------------
# error_silently_swallowed
# ---------------------------------------------------------------------------
def test_error_silently_swallowed_fires_when_text_after_error_is_clean(agent, tmp_path):
    transcript = write_transcript(tmp_path, [
        {"type": "turn"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pnpm test"}},
        {"type": "tool_result", "is_error": True, "content": "test failed"},
        {"type": "turn"},
        {"type": "text", "text": "Done. Implementation complete."},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.error_silently_swallowed" in rule_ids(r)


def test_error_acknowledged_does_not_fire(agent, tmp_path):
    transcript = write_transcript(tmp_path, [
        {"type": "turn"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pnpm test"}},
        {"type": "tool_result", "is_error": True, "content": "test failed"},
        {"type": "turn"},
        {"type": "text", "text": "Tests failed; investigating the broken assertion."},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.error_silently_swallowed" not in rule_ids(r)


# ---------------------------------------------------------------------------
# output_format_drift
# ---------------------------------------------------------------------------
REVIEWER_WITH_FORMAT = """---
name: shop-reviewer
description: "Reviews the e-Shop codebase. Use proactively after a PR opens."
model: sonnet
tools:
  - Read
  - Glob
  - Grep
---

# Shop Reviewer

## When invoked
1. Review.

## Output

Always emit:

## Critical
…

## Warnings
…

## Suggestions
…

## Constraints
- read-only.
"""


def test_output_format_drift_fires_when_sections_missing(tmp_path):
    agent_p = tmp_path / "reviewer.md"
    agent_p.write_text(REVIEWER_WITH_FORMAT, encoding="utf-8")
    transcript = write_transcript(tmp_path, [
        {"type": "turn"},
        {"type": "text", "text": "Looks fine to me."},
    ])
    r = replay.grade(str(agent_p), transcript)
    # Some of {critical, warnings, suggestions} should be missing.
    assert "behavioral.output_format_drift" in rule_ids(r)


# ---------------------------------------------------------------------------
# instruction_following_gap (claim detection)
# ---------------------------------------------------------------------------
def test_instruction_following_gap_claim_detected(agent, tmp_path):
    transcript = write_transcript(tmp_path, [
        {"type": "turn"},
        {"type": "text", "text": "I have updated services/api/users.ts and tests now pass."},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.instruction_following_gap_claim_detected" in rule_ids(r)


def test_no_claim_silent(agent, tmp_path):
    transcript = write_transcript(tmp_path, [
        {"type": "turn"},
        {"type": "text", "text": "Reading the code now."},
    ])
    r = replay.grade(agent, transcript)
    assert "behavioral.instruction_following_gap_claim_detected" not in rule_ids(r)
