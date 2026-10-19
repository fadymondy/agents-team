"""Regressions for the bugs seen while recording the usage video.

1. settings.json.partial must match the Claude Code hooks schema and use
   real hook events only (no `PostCommit`).
3. The linter must not ship a deliberately weak agent
   (`description: "Helps with stuff."`, `tools: "*"`, `model: opus`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lint"
PARTIAL = PLUGIN_ROOT / "templates" / "hooks" / "settings.json.partial"

# Hook events accepted by Claude Code (code.claude.com/docs/en/hooks).
VALID_HOOK_EVENTS = {
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification",
    "UserPromptSubmit", "SessionStart", "SessionEnd", "Stop", "SubagentStart",
    "SubagentStop", "PreCompact", "PermissionRequest", "TeammateIdle",
    "TaskCreated", "TaskCompleted",
}
TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest"}


# ---------------------------------------------------------------------------
# Bug 1 — hooks config shape
# ---------------------------------------------------------------------------
def _assert_hooks_schema(hooks: dict) -> None:
    assert isinstance(hooks, dict) and hooks
    for event, groups in hooks.items():
        assert event in VALID_HOOK_EVENTS, f"not a Claude Code hook event: {event}"
        assert isinstance(groups, list) and groups
        for group in groups:
            assert set(group) <= {"matcher", "hooks"}, group
            if "matcher" in group:
                assert isinstance(group["matcher"], str)
            assert isinstance(group["hooks"], list) and group["hooks"]
            for h in group["hooks"]:
                assert h["type"] == "command"
                assert isinstance(h["command"], str) and h["command"]


def test_settings_partial_matches_hooks_schema():
    partial = json.loads(PARTIAL.read_text(encoding="utf-8"))
    _assert_hooks_schema(partial["hooks"])
    assert "PostCommit" not in partial["hooks"]


def test_post_commit_check_wired_as_posttooluse_bash():
    hooks = json.loads(PARTIAL.read_text(encoding="utf-8"))["hooks"]
    groups = [g for g in hooks["PostToolUse"]
              if any("post-commit-check.sh" in h["command"] for h in g["hooks"])]
    assert groups and groups[0]["matcher"] == "Bash"


def test_scaffolded_settings_are_valid_and_only_wire_shipped_hooks(tmp_path):
    import scaffold  # type: ignore

    spec = json.loads((PLUGIN_ROOT.parent.parent / "examples" / "example-team.json")
                      .read_text(encoding="utf-8"))
    spec["hooks"] = ["notify", "session-init"]
    scaffold.materialize(spec, tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    _assert_hooks_schema(settings["hooks"])
    commands = [h["command"] for gs in settings["hooks"].values() for g in gs for h in g["hooks"]]
    assert all("notify.sh" in c or "session-init.sh" in c for c in commands)
    assert "TeammateIdle" not in settings["hooks"]

    # Re-running keeps existing user hooks and does not duplicate ours.
    scaffold.materialize(spec, tmp_path)
    again = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert again == settings


# ---------------------------------------------------------------------------
# Bug 3 — weak agent must not ship; good agents still must
# ---------------------------------------------------------------------------
def test_weak_agent_lands_at_c_or_d_with_revise(rule_ids):
    import lint as lint_mod  # type: ignore

    r = lint_mod.lint_file(str(FIXTURES / "weak-agent.md"))
    assert r["overall"]["grade"] in ("C", "D"), r["overall"]
    assert r["overall"]["verdict"] == "revise", r["overall"]

    ids = rule_ids(r)
    assert {"description.vague_verb_only", "description.generic_scope",
            "description.no_use_when_trigger"} <= ids
    assert "tool_hygiene.unrestricted_tools" in ids
    assert "model_fit.opus_on_generic_role" in ids

    dims = r["dimensions"]
    assert dims["description"]["score"] <= 50
    assert dims["tool_hygiene"]["score"] < 50  # tool hygiene fails outright
    assert dims["model_fit"]["score"] < 100


@pytest.mark.parametrize("name", ["good-agent.md", "good-opus-orchestrator.md"])
def test_good_agents_still_ship_at_a(name):
    import lint as lint_mod  # type: ignore

    r = lint_mod.lint_file(str(FIXTURES / name))
    assert r["overall"]["grade"] == "A", r["findings"]
    assert r["overall"]["verdict"] == "ship"


@pytest.mark.parametrize("tools_line", ['tools: "*"', "tools: *", 'tools: ["*"]', "tools: All"])
def test_unrestricted_tools_variants(lint, rule_ids, tools_line):
    agent = (FIXTURES / "good-agent.md").read_text(encoding="utf-8")
    lines = agent.splitlines()
    start = lines.index("tools:")
    end = start + 1
    while lines[end].startswith("  - "):
        end += 1
    mutated = "\n".join(lines[:start] + [tools_line] + lines[end:]) + "\n"
    r = lint(mutated)
    assert "tool_hygiene.unrestricted_tools" in rule_ids(r)
    assert r["dimensions"]["tool_hygiene"]["score"] == 0


def test_long_specific_description_without_trigger_stays_suggestion(lint):
    desc = ("Owns the Stripe checkout handlers in services/payments/, including webhook "
            "signature checks, idempotency keys and refund flows.")
    agent = (FIXTURES / "good-agent.md").read_text(encoding="utf-8")
    lines = [f'description: "{desc}"' if ln.startswith("description:") else ln
             for ln in agent.splitlines()]
    r = lint("\n".join(lines) + "\n")
    sev = {f["rule"]: f["severity"] for f in r["findings"]}
    assert sev.get("description.no_use_when_trigger") == "suggestion"
