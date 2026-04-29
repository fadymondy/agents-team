#!/usr/bin/env python3
"""
replay.py — Phase 3 behavioral grader (replay mode, skeleton).

Given (1) an agent definition file and (2) a transcript file (Claude Code
subagent JSONL at ~/.claude/projects/<slug>/subagents/agent-*.jsonl),
score the transcript against the agent's stated promises.

What it grades (skeleton, deterministic checks only):
- tool_whitelist_adherence: every tool call in the transcript appears in
  the agent's `tools` field.
- step_efficiency: turn count vs an expected band (configurable).

Out-of-scope for v0.1 skeleton (TODO in v0.2):
- Domain adherence (LLM-judge over tool-call paths).
- Instruction-following gap (judge compares agent's claim vs env state).
- Self-correction signal.

Usage:
    replay.py <agent-file> <transcript-file>
    replay.py --max-turns 30 <agent> <transcript>

Output: v1-schema JSON with produced_by="behavioral" + behavioral_metadata.
Exit codes match lint.py / judge.py: 0 ship, 1 revise, 2 reject.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lint import (  # type: ignore
    DIMENSIONS,
    DIMENSION_WEIGHTS_AGENT,
    DIMENSION_WEIGHTS_SKILL,
    SCHEMA_VERSION,
    Finding,
    grade_for,
    parse_file,
    score_for,
    verdict_for,
    _infer_kind,
)


def parse_transcript(path: str) -> list[dict]:
    """Read JSONL transcript; return list of event dicts. Robust to malformed lines."""
    events = []
    with open(path, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError as e:
                events.append({"_parse_error": str(e), "_line": line_no, "_raw": raw[:200]})
    return events


def collect_tool_calls(events: list[dict]) -> list[tuple[int, str, dict]]:
    """
    Extract tool calls from transcript events.
    Returns list of (turn_index, tool_name, params).
    Format is best-effort: Claude Code transcripts use a few shapes.
    """
    out = []
    turn = 0
    for ev in events:
        if "_parse_error" in ev:
            continue
        # Heuristics across known transcript shapes
        et = ev.get("type") or ev.get("event")
        if et in ("turn", "message"):
            turn += 1
        # Tool use shape: { type: "tool_use", name, input }
        if ev.get("type") == "tool_use" and "name" in ev:
            out.append((turn, ev["name"], ev.get("input", {})))
            continue
        # Anthropic SDK content-block shape
        for block in ev.get("content", []) if isinstance(ev.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append((turn, block.get("name", "?"), block.get("input", {})))
        # Claude Code wrapper shape: { tool: { name, params } }
        tool = ev.get("tool")
        if isinstance(tool, dict) and "name" in tool:
            out.append((turn, tool["name"], tool.get("params", {})))
    return out


def grade(agent_path: str, transcript_path: str, max_turns: int = 50) -> dict:
    pf = parse_file(agent_path)
    kind = _infer_kind(agent_path, pf.frontmatter)
    weights = DIMENSION_WEIGHTS_AGENT if kind == "agent" else DIMENSION_WEIGHTS_SKILL

    events = parse_transcript(transcript_path)
    tool_calls = collect_tool_calls(events)

    findings: list[Finding] = []
    behavioral_metadata = {
        "transcript_path": transcript_path,
        "turn_count": max((tc[0] for tc in tool_calls), default=0),
        "tool_call_count": len(tool_calls),
    }

    # Whitelist adherence
    declared_tools = pf.frontmatter.get("tools") or []
    if isinstance(declared_tools, str):
        declared_tools = [t.strip() for t in declared_tools.split(",") if t.strip()]
    declared_set = set(declared_tools)
    if declared_set:
        violations = sorted({name for _, name, _ in tool_calls if name not in declared_set})
        if violations:
            findings.append(Finding(
                severity="critical",
                rule="behavioral.tool_whitelist_violation",
                message=(
                    f"Transcript uses tools not in the agent's `tools` whitelist: "
                    f"{violations}."
                ),
                evidence={"transcript": transcript_path, "violations": violations,
                          "declared": sorted(declared_set)},
                fix=f"Either add the missing tools to the agent definition or remove the calls.",
                source="https://code.claude.com/docs/en/sub-agents",
                produced_by="behavioral",
            ))
    else:
        findings.append(Finding(
            severity="suggestion",
            rule="behavioral.no_declared_tools",
            message="Agent has no declared `tools` field, so whitelist adherence cannot be measured.",
            evidence={"frontmatter_field": "tools"},
            fix="Add an explicit `tools:` list to make whitelist scoring possible.",
            source="https://code.claude.com/docs/en/sub-agents",
            produced_by="behavioral",
        ))

    # Step efficiency
    if behavioral_metadata["turn_count"] > max_turns:
        findings.append(Finding(
            severity="warning",
            rule="behavioral.step_efficiency_exceeded",
            message=(
                f"Turn count {behavioral_metadata['turn_count']} exceeds the expected "
                f"band of {max_turns}. Look for redundant reads or tool-call loops."
            ),
            evidence={"transcript": transcript_path, "turns": behavioral_metadata["turn_count"]},
            fix="Reduce loops; batch independent calls in one turn.",
            source="https://www.braintrust.dev/articles/ai-agent-evaluation-framework",
            produced_by="behavioral",
        ))

    # Aggregate per-dimension scores. v0.1 skeleton: only tool_hygiene gets a
    # behavioral score; other dimensions stay at 100 (untouched by replay).
    findings_by_dim = {d: [] for d in DIMENSIONS}
    for f in findings:
        if f.rule.startswith("behavioral.tool_") or f.rule.startswith("behavioral.no_declared_tools"):
            findings_by_dim["tool_hygiene"].append(f)
        elif f.rule.startswith("behavioral.step_"):
            findings_by_dim["body_structure"].append(f)
        else:
            findings_by_dim["anti_patterns"].append(f)

    dimensions_out = {}
    overall_acc = 0.0
    for dim in DIMENSIONS:
        s = score_for(findings_by_dim[dim])
        dimensions_out[dim] = {
            "score": s,
            "weight": weights[dim],
            "findings": [f.to_dict() for f in findings_by_dim[dim]],
        }
        overall_acc += s * weights[dim]

    overall_score = round(overall_acc)
    overall_grade = grade_for(overall_score)
    overall_verdict = verdict_for(overall_score, all_findings=findings)

    return {
        "agent": pf.frontmatter.get("name") or os.path.splitext(os.path.basename(agent_path))[0],
        "path": agent_path,
        "kind": kind,
        "overall": {"score": overall_score, "grade": overall_grade, "verdict": overall_verdict},
        "dimensions": dimensions_out,
        "findings": [f.to_dict() for f in findings],
        "produced_by": "behavioral",
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "behavioral_metadata": behavioral_metadata,
        "schema_version": SCHEMA_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("agent")
    p.add_argument("transcript")
    p.add_argument("--max-turns", type=int, default=50)
    args = p.parse_args(argv)

    if not os.path.isfile(args.agent):
        print(f"replay.py: not a file: {args.agent}", file=sys.stderr)
        return 66
    if not os.path.isfile(args.transcript):
        print(f"replay.py: not a file: {args.transcript}", file=sys.stderr)
        return 66

    report = grade(args.agent, args.transcript, max_turns=args.max_turns)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return {"ship": 0, "revise": 1, "reject": 2}.get(report["overall"]["verdict"], 0)


if __name__ == "__main__":
    sys.exit(main())
