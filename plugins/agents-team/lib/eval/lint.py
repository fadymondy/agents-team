#!/usr/bin/env python3
"""
lint.py — static linter for Claude Code agent + skill files.

Phase 1 of the agents-team evaluator. Parses a Markdown file with YAML
frontmatter and applies a deterministic, citation-backed rule set. Emits JSON
conforming to lib/eval/schema/v1.json.

Usage:
    lint.py <path-to-agent-or-skill.md>           # one file → JSON to stdout
    lint.py --kind=skill <path>                   # treat as SKILL.md
    lint.py --strict <path>                       # promote suggestions to warnings
    lint.py --version

Anti-goals (from docs/architecture):
- Do not auto-rewrite agent files.
- Every finding cites a source URL.
- Stylistic preferences are NOT failures (only with --strict).

Zero third-party deps; only stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional


SCHEMA_VERSION = "1.0.0"
ANTHROPIC_SUBAGENTS = "https://code.claude.com/docs/en/sub-agents"
ANTHROPIC_SKILLS = "https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices"
DEMYSTIFYING_EVALS = "https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents"

DIMENSIONS = (
    "frontmatter",
    "description",
    "tool_hygiene",
    "model_fit",
    "body_structure",
    "anti_patterns",
)
DIMENSION_WEIGHTS_AGENT = {
    "frontmatter": 0.15,
    "description": 0.25,
    "tool_hygiene": 0.15,
    "model_fit": 0.10,
    "body_structure": 0.20,
    "anti_patterns": 0.15,
}
# Skills weight description higher (it's the trigger) and tool_hygiene lower.
DIMENSION_WEIGHTS_SKILL = {
    "frontmatter": 0.20,
    "description": 0.30,
    "tool_hygiene": 0.10,
    "model_fit": 0.05,
    "body_structure": 0.25,
    "anti_patterns": 0.10,
}

RESERVED_NAME_PREFIXES = ("anthropic-", "claude-")
RETIRED_MODEL_IDS = (
    "claude-1",
    "claude-2",
    "claude-instant",
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
    "claude-3-5-sonnet",
)
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
ORCHESTRATOR_INDICATORS = ("orchestrator", "orchestrate", "delegate", "route")
REVIEW_INDICATORS = ("review", "audit", "analyze", "report", "linter", "evaluator", "monitor")
VAGUE_VERBS_ALONE = re.compile(
    r"^\s*(helps?|assists?|supports?)\b[^.]{0,40}$", re.IGNORECASE
)
FIRST_OR_SECOND_PERSON = re.compile(
    r"\b(I\s+(can|will|help)|my\s+job|let\s+me|you\s+can\s+use\s+(this|me)|use\s+me\b)",
    re.IGNORECASE,
)
USE_WHEN_TRIGGER = re.compile(
    r"\b(use\s+(when|proactively|immediately(\s+after)?)|MUST\s+BE\s+USED)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    severity: str
    rule: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    fix: Optional[str] = None
    source: Optional[str] = None
    produced_by: str = "static"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "produced_by": self.produced_by,
        }
        if self.evidence:
            d["evidence"] = self.evidence
        if self.fix is not None:
            d["fix"] = self.fix
        if self.source is not None:
            d["source"] = self.source
        return d


@dataclass
class ParsedFile:
    path: str
    raw: str
    frontmatter: dict[str, Any]
    body: str
    body_line_offset: int  # absolute file line where body starts (1-indexed)
    fm_lines: dict[str, int]  # frontmatter key → 1-indexed file line


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def parse_file(path: str) -> ParsedFile:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    lines = raw.splitlines()
    fm: dict[str, Any] = {}
    fm_lines: dict[str, int] = {}
    body_start = 0  # index into lines

    if lines and lines[0].strip() == "---":
        # Find closing fence
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            fm, fm_lines = parse_frontmatter(lines[1:end], offset=2)
            body_start = end + 1

    body = "\n".join(lines[body_start:])
    return ParsedFile(
        path=path,
        raw=raw,
        frontmatter=fm,
        body=body,
        body_line_offset=body_start + 1,
        fm_lines=fm_lines,
    )


_KV_LINE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<value>.*)$")
_LIST_ITEM = re.compile(r"^\s*-\s+(?P<value>.+?)\s*$")


def parse_frontmatter(
    lines: list[str], offset: int = 1
) -> tuple[dict[str, Any], dict[str, int]]:
    """Permissive YAML subset parser — handles flat keys, scalar values,
    and simple list-of-scalars. Returns (kv-dict, key→source-line-number)."""
    out: dict[str, Any] = {}
    line_of: dict[str, int] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip blanks and comments
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = _KV_LINE.match(line)
        if not m:
            i += 1
            continue
        key = m.group("key")
        value = m.group("value").strip()
        line_of[key] = offset + i
        if value == "":
            # Could be a list / nested object. We support list-of-scalars only.
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    j += 1
                    continue
                im = _LIST_ITEM.match(nxt)
                if im is None:
                    break
                items.append(_strip_quotes(im.group("value")))
                j += 1
            out[key] = items
            i = j
            continue
        # Inline scalar / list / bool / int
        out[key] = _coerce_scalar(value)
        i += 1
    return out, line_of


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _coerce_scalar(v: str) -> Any:
    s = v.strip()
    if s.startswith("[") and s.endswith("]"):
        # inline list
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(x.strip()) for x in inner.split(",")]
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return _strip_quotes(s)


# --------------------------------------------------------------------------- #
# Rule registry
# --------------------------------------------------------------------------- #
RuleFn = Callable[[ParsedFile, str], Iterable[Finding]]
_REGISTRY: list[tuple[str, RuleFn]] = []


def rule(dimension: str) -> Callable[[RuleFn], RuleFn]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension: {dimension}")

    def deco(fn: RuleFn) -> RuleFn:
        _REGISTRY.append((dimension, fn))
        return fn

    return deco


def fm_evidence(pf: ParsedFile, key: str, value: Any = None) -> dict[str, Any]:
    ev: dict[str, Any] = {"frontmatter_field": key}
    if key in pf.fm_lines:
        ev["file"] = pf.path
        ev["line"] = pf.fm_lines[key]
    if value is not None:
        ev["value"] = value
    return ev


# --------------------------------------------------------------------------- #
# Rules: frontmatter
# --------------------------------------------------------------------------- #
@rule("frontmatter")
def fm_required_name(pf: ParsedFile, kind: str):
    name = pf.frontmatter.get("name")
    if not name:
        yield Finding(
            severity="critical",
            rule="frontmatter.name_missing",
            message="`name` is required in frontmatter.",
            evidence={"frontmatter_field": "name"},
            fix="Add `name: <slug>` to the frontmatter.",
            source=ANTHROPIC_SKILLS if kind == "skill" else ANTHROPIC_SUBAGENTS,
        )
        return
    name_str = str(name)
    if kind == "skill" and len(name_str) > 64:
        yield Finding(
            severity="critical",
            rule="frontmatter.name_too_long",
            message=f"`name` must be ≤64 chars (got {len(name_str)}).",
            evidence=fm_evidence(pf, "name", name_str),
            fix="Shorten the name to ≤64 chars.",
            source=ANTHROPIC_SKILLS,
        )
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name_str):
        yield Finding(
            severity="critical",
            rule="frontmatter.name_invalid_chars",
            message="`name` must be lowercase letters/digits/hyphens only.",
            evidence=fm_evidence(pf, "name", name_str),
            fix=f"Rename to e.g. `{re.sub(r'[^a-z0-9-]+', '-', name_str.lower()).strip('-')}`.",
            source=ANTHROPIC_SUBAGENTS,
        )
    if any(name_str.startswith(p) for p in RESERVED_NAME_PREFIXES):
        yield Finding(
            severity="critical",
            rule="frontmatter.name_reserved",
            message=f"`name` uses a reserved prefix: {name_str}.",
            evidence=fm_evidence(pf, "name", name_str),
            fix="Pick a name that does not start with `anthropic-` or `claude-`.",
            source=ANTHROPIC_SKILLS,
        )


@rule("frontmatter")
def fm_required_description(pf: ParsedFile, kind: str):
    desc = pf.frontmatter.get("description")
    if not desc:
        yield Finding(
            severity="critical",
            rule="frontmatter.description_missing",
            message="`description` is required in frontmatter.",
            evidence={"frontmatter_field": "description"},
            fix="Add a description that says WHEN to use this and WHAT it does (third person).",
            source=ANTHROPIC_SUBAGENTS if kind == "agent" else ANTHROPIC_SKILLS,
        )
        return
    desc_str = str(desc)
    if kind == "skill" and len(desc_str) > 1024:
        yield Finding(
            severity="critical",
            rule="frontmatter.description_too_long",
            message=f"Skill `description` must be ≤1024 chars (got {len(desc_str)}).",
            evidence=fm_evidence(pf, "description", f"{desc_str[:80]}…"),
            fix="Shorten or move details to the body.",
            source=ANTHROPIC_SKILLS,
        )


@rule("frontmatter")
def fm_model_not_retired(pf: ParsedFile, kind: str):
    model = pf.frontmatter.get("model")
    if not model:
        return
    model_str = str(model).strip()
    for retired in RETIRED_MODEL_IDS:
        if model_str.startswith(retired):
            yield Finding(
                severity="warning",
                rule="frontmatter.model_retired",
                message=f"`model: {model_str}` references a retired model family.",
                evidence=fm_evidence(pf, "model", model_str),
                fix="Use a current model alias (e.g. `opus`, `sonnet`, `haiku`) or a current full ID.",
                source=ANTHROPIC_SUBAGENTS,
            )
            return


# --------------------------------------------------------------------------- #
# Rules: description
# --------------------------------------------------------------------------- #
@rule("description")
def desc_length_band(pf: ParsedFile, kind: str):
    desc = pf.frontmatter.get("description")
    if not desc:
        return
    desc_str = str(desc)
    n = len(desc_str)
    if kind == "agent" and (n < 80 or n > 400):
        yield Finding(
            severity="warning",
            rule="description.length_outside_band",
            message=(
                f"Agent description length {n} chars is outside the 80–400 band. "
                "Too short → ambiguous routing; too long → wastes routing context."
            ),
            evidence=fm_evidence(pf, "description", desc_str),
            fix="Aim for one or two sentences with both WHAT and WHEN.",
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("description")
def desc_third_person(pf: ParsedFile, kind: str):
    desc = pf.frontmatter.get("description")
    if not desc:
        return
    desc_str = str(desc)
    m = FIRST_OR_SECOND_PERSON.search(desc_str)
    if m:
        yield Finding(
            severity="warning",
            rule="description.first_or_second_person",
            message=(
                "Description uses first/second person (e.g. \"I help…\", \"you can use…\"). "
                "Anthropic guidance: write descriptions in third person."
            ),
            evidence=fm_evidence(pf, "description", m.group(0)),
            fix='Rewrite in third person ("Reviews code for…" not "I review code for…").',
            source=ANTHROPIC_SKILLS,
        )


@rule("description")
def desc_use_when_trigger(pf: ParsedFile, kind: str):
    desc = pf.frontmatter.get("description")
    if not desc:
        return
    desc_str = str(desc)
    if not USE_WHEN_TRIGGER.search(desc_str):
        yield Finding(
            severity="suggestion",
            rule="description.no_use_when_trigger",
            message=(
                'Description does not contain a "use when" / "use proactively" / '
                '"MUST BE USED" trigger phrase, so the orchestrator may under-delegate.'
            ),
            evidence=fm_evidence(pf, "description"),
            fix='Add e.g. "Use immediately after writing or modifying code."',
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("description")
def desc_no_vague_verb_only(pf: ParsedFile, kind: str):
    desc = pf.frontmatter.get("description")
    if not desc:
        return
    desc_str = str(desc).strip()
    if VAGUE_VERBS_ALONE.match(desc_str):
        yield Finding(
            severity="warning",
            rule="description.vague_verb_only",
            message=(
                "Description starts with a vague verb (helps/assists/supports) "
                "without a specific domain noun."
            ),
            evidence=fm_evidence(pf, "description", desc_str),
            fix='Replace with a domain-specific phrase ("Reviews TypeScript handlers for…").',
            source=ANTHROPIC_SUBAGENTS,
        )


# --------------------------------------------------------------------------- #
# Rules: tool_hygiene
# --------------------------------------------------------------------------- #
@rule("tool_hygiene")
def tools_field_present(pf: ParsedFile, kind: str):
    tools_key = "tools" if kind == "agent" else "allowed-tools"
    if tools_key not in pf.frontmatter:
        yield Finding(
            severity="critical",
            rule="tool_hygiene.tools_omitted",
            message=(
                f"`{tools_key}` is not set — the {kind} silently inherits every tool "
                "from the parent (the most common over-grant anti-pattern)."
            ),
            evidence={"frontmatter_field": tools_key},
            fix=f"Add an explicit `{tools_key}:` list, even if it is the full set you actually need.",
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("tool_hygiene")
def tools_write_on_review_role(pf: ParsedFile, kind: str):
    if kind != "agent":
        return
    tools = pf.frontmatter.get("tools") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    desc = str(pf.frontmatter.get("description", ""))
    body_head = pf.body[:2000]
    name = str(pf.frontmatter.get("name", ""))
    # Orchestrators are not reviewers — they delegate but may also write plan
    # files; treat them as a separate archetype.
    is_orchestrator = any(
        re.search(rf"\b{ind}\b", desc + " " + body_head, re.IGNORECASE)
        for ind in ORCHESTRATOR_INDICATORS
    )
    if is_orchestrator:
        return
    # Stronger reviewer signal: name contains a reviewer noun, OR description
    # starts with a reviewer verb (Reviews / Audits / Lints / Monitors).
    name_signal = bool(re.search(r"(reviewer|auditor|linter|monitor|evaluator|watcher)", name, re.IGNORECASE))
    desc_verb = bool(re.match(
        r"\s*(reviews|audits|lints|monitors|evaluates|watches)\b",
        desc,
        re.IGNORECASE,
    ))
    is_reviewer = name_signal or desc_verb
    write_tools_in_use = sorted(t for t in tools if t in WRITE_TOOLS)
    if is_reviewer and write_tools_in_use:
        yield Finding(
            severity="critical",
            rule="tool_hygiene.write_on_review_role",
            message=(
                "Description / body indicates a review or audit role, "
                f"but `tools` includes write tools: {write_tools_in_use}."
            ),
            evidence=fm_evidence(pf, "tools", tools),
            fix="Remove write tools; reviewers should be read-only.",
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("tool_hygiene")
def tools_bash_without_safeguard(pf: ParsedFile, kind: str):
    if kind != "agent":
        return
    tools = pf.frontmatter.get("tools") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    if "Bash" not in tools:
        return
    has_perm_mode = "permissionMode" in pf.frontmatter
    body = pf.body
    has_pre_tool_hook = bool(re.search(r"PreToolUse", body))
    if has_perm_mode or has_pre_tool_hook:
        return
    desc = str(pf.frontmatter.get("description", ""))
    if any(re.search(rf"\b{ind}\b", desc, re.IGNORECASE) for ind in REVIEW_INDICATORS):
        yield Finding(
            severity="warning",
            rule="tool_hygiene.bash_without_safeguard_on_readonly",
            message=(
                "Read-only role grants `Bash` without `permissionMode` "
                "or a `PreToolUse` hook to constrain it."
            ),
            evidence=fm_evidence(pf, "tools", tools),
            fix="Either drop Bash, set `permissionMode`, or wire a PreToolUse hook to gate it.",
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("tool_hygiene")
def tools_agent_only_for_orchestrator(pf: ParsedFile, kind: str):
    if kind != "agent":
        return
    tools = pf.frontmatter.get("tools") or []
    if "Agent" not in tools:
        return
    desc = str(pf.frontmatter.get("description", ""))
    body = pf.body[:3000]
    if any(
        re.search(rf"\b{ind}\b", desc + " " + body, re.IGNORECASE)
        for ind in ORCHESTRATOR_INDICATORS
    ):
        return
    yield Finding(
        severity="suggestion",
        rule="tool_hygiene.agent_tool_on_leaf",
        message=(
            "`Agent` is granted but the agent does not look like an orchestrator. "
            "Sub-agents cannot dispatch other sub-agents anyway."
        ),
        evidence=fm_evidence(pf, "tools"),
        fix="Drop `Agent` from the tool list unless this agent delegates to others.",
        source=ANTHROPIC_SUBAGENTS,
    )


# --------------------------------------------------------------------------- #
# Rules: model_fit
# --------------------------------------------------------------------------- #
@rule("model_fit")
def model_fit_role(pf: ParsedFile, kind: str):
    model = str(pf.frontmatter.get("model", "")).lower()
    desc = str(pf.frontmatter.get("description", "")).lower()

    # Read-only / lookup signal: matched in the description (where role is declared).
    is_readonly = any(
        re.search(rf"\b{re.escape(ind)}\b", desc)
        for ind in ("monitor", "monitors", "watches", "reviews", "audits", "lints",
                    "lookup", "status check", "triages", "triage")
    )
    # Architect signal: only fire on active-voice verbs in the description.
    is_architect = any(
        re.search(rf"\b{re.escape(ind)}\b", desc)
        for ind in ("architecture", "trade-off", "trade off", "orchestrates",
                    "orchestrator", "delegates", "plans", "routes", "dispatches")
    )

    if "opus" in model and is_readonly and not is_architect:
        yield Finding(
            severity="warning",
            rule="model_fit.opus_on_readonly_role",
            message=(
                "Role appears read-only / triage but uses Opus. "
                "Anthropic guidance: read-only/lookup roles → Haiku; Sonnet for code; Opus for hard reasoning."
            ),
            evidence=fm_evidence(pf, "model", model),
            fix="Switch to Haiku (cheap, fast) unless the role does multi-step reasoning.",
            source=ANTHROPIC_SUBAGENTS,
        )
    if "haiku" in model and is_architect:
        yield Finding(
            severity="warning",
            rule="model_fit.haiku_on_reasoning_role",
            message=(
                "Role does architecture / multi-step reasoning but uses Haiku, "
                "which often loops or hallucinates on hard reasoning."
            ),
            evidence=fm_evidence(pf, "model", model),
            fix="Move to Sonnet or Opus depending on the reasoning depth.",
            source=ANTHROPIC_SUBAGENTS,
        )


# --------------------------------------------------------------------------- #
# Rules: body_structure
# --------------------------------------------------------------------------- #
@rule("body_structure")
def body_when_invoked_section(pf: ParsedFile, kind: str):
    if kind != "agent":
        return
    if not re.search(r"^#{1,3}\s+(when\s+invoked|procedure|workflow|process)\b",
                     pf.body, re.IGNORECASE | re.MULTILINE):
        yield Finding(
            severity="suggestion",
            rule="body_structure.no_when_invoked_section",
            message='Body has no "When invoked" / procedure / workflow heading.',
            evidence={"file": pf.path, "line": pf.body_line_offset},
            fix='Add a numbered "## When invoked" section listing the agent\'s procedure.',
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("body_structure")
def body_constraints_section(pf: ParsedFile, kind: str):
    if kind != "agent":
        return
    if not re.search(
        r"^#{1,3}\s+(constraints|guardrails|do\s+not|don['']t|anti-?patterns|out\s+of\s+scope)\b",
        pf.body,
        re.IGNORECASE | re.MULTILINE,
    ):
        yield Finding(
            severity="suggestion",
            rule="body_structure.no_constraints_section",
            message="Body has no constraints / guardrails / anti-patterns section.",
            evidence={"file": pf.path, "line": pf.body_line_offset},
            fix='Add a "## Constraints" section listing what the agent must NOT do.',
            source=ANTHROPIC_SUBAGENTS,
        )


@rule("body_structure")
def body_skill_size(pf: ParsedFile, kind: str):
    if kind != "skill":
        return
    line_count = pf.body.count("\n") + 1
    if line_count > 500:
        yield Finding(
            severity="warning",
            rule="body_structure.skill_body_too_long",
            message=f"Skill body is {line_count} lines; Anthropic guidance: <500 lines (use progressive disclosure).",
            evidence={"file": pf.path, "line": pf.body_line_offset},
            fix="Move detail into `references/` or `scripts/` referenced from SKILL.md.",
            source=ANTHROPIC_SKILLS,
        )


@rule("body_structure")
def body_skill_toc_when_long(pf: ParsedFile, kind: str):
    if kind != "skill":
        return
    line_count = pf.body.count("\n") + 1
    if line_count > 100 and not re.search(
        r"(?i)^#{1,3}\s+(table\s+of\s+contents|toc)\b|^\s*-\s+\[.+?\]\(#",
        pf.body,
        re.MULTILINE,
    ):
        yield Finding(
            severity="suggestion",
            rule="body_structure.skill_no_toc_when_long",
            message=f"Skill body is {line_count} lines but has no table of contents.",
            evidence={"file": pf.path, "line": pf.body_line_offset},
            fix='Add a "## Table of contents" section linking to internal anchors.',
            source=ANTHROPIC_SKILLS,
        )


# --------------------------------------------------------------------------- #
# Rules: anti_patterns
# --------------------------------------------------------------------------- #
@rule("anti_patterns")
def antipattern_prompt_injection_smell(pf: ParsedFile, kind: str):
    body = pf.body
    suspects = [
        (r"<\s*system\s*>", "anti_patterns.injection_system_tag",
         "Body contains a `<system>` tag — possible prompt-injection vector."),
        (r"ignore\s+(prior|all|previous)\s+instructions", "anti_patterns.injection_ignore_prior",
         '"ignore prior/all/previous instructions" is a classic injection phrase.'),
        (r"respond\s+only\s+with", "anti_patterns.injection_respond_only",
         '"respond only with…" overrides the user — review carefully.'),
    ]
    for pattern, rule_id, message in suspects:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            line_idx = body[: m.start()].count("\n")
            yield Finding(
                severity="warning",
                rule=rule_id,
                message=message,
                evidence={"file": pf.path, "line": pf.body_line_offset + line_idx, "match": m.group(0)},
                fix="Remove or rephrase. Constraints belong in the `## Constraints` section, not as override directives.",
                source=ANTHROPIC_SUBAGENTS,
            )


@rule("anti_patterns")
def antipattern_hardcoded_absolute_paths(pf: ParsedFile, kind: str):
    if kind != "skill":
        return
    matches = list(re.finditer(r"(?:/Users/[^\s)\"']+|[A-Z]:\\\\[^\s)\"']+)", pf.body))
    if not matches:
        return
    first = matches[0]
    line_idx = pf.body[: first.start()].count("\n")
    yield Finding(
        severity="warning",
        rule="anti_patterns.hardcoded_absolute_path",
        message=f"Body contains {len(matches)} hardcoded absolute path(s) (e.g. `{first.group(0)}`).",
        evidence={"file": pf.path, "line": pf.body_line_offset + line_idx, "match": first.group(0)},
        fix="Use placeholders like `{{repo_root}}` or document the path as user-configurable.",
        source=ANTHROPIC_SKILLS,
    )


@rule("anti_patterns")
def antipattern_role_tool_contradiction(pf: ParsedFile, kind: str):
    if kind != "agent":
        return
    body = pf.body[:3000].lower()
    tools = pf.frontmatter.get("tools") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    declares_readonly = bool(re.search(r"\bread[- ]only\b", body))
    has_write_tool = any(t in WRITE_TOOLS for t in tools)
    if declares_readonly and has_write_tool:
        yield Finding(
            severity="critical",
            rule="anti_patterns.body_says_readonly_tools_have_write",
            message='Body says "read-only" but `tools` includes write tools.',
            evidence=fm_evidence(pf, "tools", tools),
            fix="Either remove the write tools or remove the read-only claim.",
            source=ANTHROPIC_SUBAGENTS,
        )


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def lint_file(path: str, kind: Optional[str] = None, strict: bool = False) -> dict[str, Any]:
    pf = parse_file(path)
    if kind is None:
        kind = _infer_kind(path, pf.frontmatter)

    weights = DIMENSION_WEIGHTS_AGENT if kind == "agent" else DIMENSION_WEIGHTS_SKILL

    findings_by_dim: dict[str, list[Finding]] = {d: [] for d in DIMENSIONS}
    for dim, fn in _REGISTRY:
        for finding in fn(pf, kind):
            if strict and finding.severity == "suggestion":
                finding.severity = "warning"
            findings_by_dim[dim].append(finding)

    dimensions_out: dict[str, dict[str, Any]] = {}
    overall_score_acc = 0.0
    for dim in DIMENSIONS:
        score = score_for(findings_by_dim[dim])
        dimensions_out[dim] = {
            "score": score,
            "weight": weights[dim],
            "findings": [f.to_dict() for f in findings_by_dim[dim]],
        }
        overall_score_acc += score * weights[dim]

    overall_score = round(overall_score_acc)
    overall_grade = grade_for(overall_score)
    overall_verdict = verdict_for(overall_score, all_findings=sum(findings_by_dim.values(), []))

    all_findings_flat = sorted(
        sum(findings_by_dim.values(), []),
        key=lambda f: ("critical", "warning", "suggestion").index(f.severity),
    )

    return {
        "agent": pf.frontmatter.get("name") or os.path.splitext(os.path.basename(path))[0],
        "path": path,
        "kind": kind,
        "overall": {
            "score": overall_score,
            "grade": overall_grade,
            "verdict": overall_verdict,
        },
        "dimensions": dimensions_out,
        "findings": [f.to_dict() for f in all_findings_flat],
        "produced_by": "static",
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": SCHEMA_VERSION,
    }


_SKILL_FRONTMATTER_HINTS = ("disable-model-invocation", "user-invocable", "argument-hint", "allowed-tools")


def _infer_kind(path: str, frontmatter: dict[str, Any]) -> str:
    base = os.path.basename(path).upper()
    if base == "SKILL.MD" or base.endswith("/SKILL.MD"):
        return "skill"
    if any(k in frontmatter for k in _SKILL_FRONTMATTER_HINTS):
        return "skill"
    if "skill" in os.path.basename(path).lower() and "tools" not in frontmatter:
        return "skill"
    return "agent"


_SEVERITY_PENALTY = {"critical": 40, "warning": 15, "suggestion": 5}


def score_for(findings: list[Finding]) -> int:
    score = 100
    for f in findings:
        score -= _SEVERITY_PENALTY.get(f.severity, 5)
    return max(0, min(100, score))


def grade_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 65:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def verdict_for(score: int, all_findings: list[Finding]) -> str:
    has_critical = any(f.severity == "critical" for f in all_findings)
    if has_critical or score < 50:
        return "reject"
    if score < 75:
        return "revise"
    return "ship"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", nargs="?", help="Path to agent or skill file")
    p.add_argument("--kind", choices=("agent", "skill"), default=None,
                   help="Force file kind (default: infer from filename — SKILL.md is skill, else agent)")
    p.add_argument("--strict", action="store_true",
                   help="Promote suggestion-severity findings to warnings.")
    p.add_argument("--version", action="store_true", help="Print schema version and exit.")
    args = p.parse_args(argv)

    if args.version:
        print(SCHEMA_VERSION)
        return 0
    if not args.path:
        p.print_help(sys.stderr)
        return 64
    if not os.path.isfile(args.path):
        print(f"lint.py: not a file: {args.path}", file=sys.stderr)
        return 66

    report = lint_file(args.path, kind=args.kind, strict=args.strict)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")

    verdict = report["overall"]["verdict"]
    return {"ship": 0, "revise": 1, "reject": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
