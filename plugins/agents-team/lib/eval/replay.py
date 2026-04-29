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


# ---------------------------------------------------------------------------
# Behavioral signals — extracted helpers used by grade().
# ---------------------------------------------------------------------------
import re  # noqa: E402  (intentionally local to behavioral helpers)


_OWNED_PATH_RE = re.compile(
    r"(?:owned_paths|owns)[\"'`:\s]+`?([^\s`\"',]+/?)`?",
    re.IGNORECASE,
)
_PATH_FROM_INPUT_KEYS = ("path", "file_path", "filename", "filePath")
_CLAIM_PATTERNS = [
    re.compile(r"\bI\s+(?:have\s+)?(?:updated|modified|created|added)\s+`?([^\s`,]+)`?", re.IGNORECASE),
    re.compile(r"\bcreated\s+(?:the\s+)?file\s+`?([^\s`,]+)`?", re.IGNORECASE),
    re.compile(r"\b(?:tests?\s+now\s+pass|all\s+tests?\s+pass)\b", re.IGNORECASE),
    re.compile(r"\bpushed\s+(?:to\s+)?(?:branch\s+)?`?([^\s`,]+)`?", re.IGNORECASE),
]
_FORMAT_SECTION_RE = re.compile(r"^#{1,4}\s+(critical|warnings?|suggestions?)\b", re.IGNORECASE | re.MULTILINE)


def collect_text_blocks(events: list[dict]) -> list[tuple[int, str]]:
    """Pull assistant text turns out of a transcript. (turn_index, text)."""
    out: list[tuple[int, str]] = []
    turn = 0
    for ev in events:
        if "_parse_error" in ev:
            continue
        et = ev.get("type") or ev.get("event")
        if et in ("turn", "message"):
            turn += 1
        # Top-level text shape
        if ev.get("type") == "text" and isinstance(ev.get("text"), str):
            out.append((turn, ev["text"]))
        # Anthropic content blocks
        for block in ev.get("content", []) if isinstance(ev.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                out.append((turn, block["text"]))
        # Claude Code wrapper: { role: "assistant", content: "<string>" }
        if ev.get("role") == "assistant" and isinstance(ev.get("content"), str):
            out.append((turn, ev["content"]))
    return out


def collect_tool_results(events: list[dict]) -> list[dict]:
    """Pull tool results so we can detect errors. Returns dicts with
    tool_use_id / is_error / content keys when present."""
    out: list[dict] = []
    for ev in events:
        if "_parse_error" in ev:
            continue
        if ev.get("type") == "tool_result":
            out.append(ev)
            continue
        for block in ev.get("content", []) if isinstance(ev.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                out.append(block)
    return out


def extract_owned_paths(pf) -> list[str]:
    """Pull owned-path hints from an agent's frontmatter description + body."""
    paths: list[str] = []
    desc = str(pf.frontmatter.get("description", ""))
    body = pf.body[:4000]
    for src in (desc, body):
        for m in _OWNED_PATH_RE.finditer(src):
            p = m.group(1).strip().rstrip("/")
            if p and p not in paths:
                paths.append(p)
    return paths


def _path_from_input(name: str, params: dict) -> str | None:
    for key in _PATH_FROM_INPUT_KEYS:
        v = params.get(key)
        if isinstance(v, str):
            return v
    # Bash: the command itself doesn't have a clean path arg; skip.
    return None


def grade(agent_path: str, transcript_path: str, max_turns: int = 50) -> dict:
    pf = parse_file(agent_path)
    kind = _infer_kind(agent_path, pf.frontmatter)
    weights = DIMENSION_WEIGHTS_AGENT if kind == "agent" else DIMENSION_WEIGHTS_SKILL

    events = parse_transcript(transcript_path)
    tool_calls = collect_tool_calls(events)
    text_blocks = collect_text_blocks(events)
    tool_results = collect_tool_results(events)

    findings: list[Finding] = []
    behavioral_metadata = {
        "transcript_path": transcript_path,
        "turn_count": max((tc[0] for tc in tool_calls), default=0),
        "tool_call_count": len(tool_calls),
        "text_block_count": len(text_blocks),
    }

    # ----- domain_adherence (heuristic, deterministic) ----- #
    owned_paths = extract_owned_paths(pf)
    if owned_paths:
        out_of_scope = []
        for turn, name, params in tool_calls:
            path = _path_from_input(name, params)
            if path and not any(path.startswith(op) or op in path for op in owned_paths):
                out_of_scope.append((turn, name, path))
        if len(out_of_scope) >= 2:
            findings.append(Finding(
                severity="warning",
                rule="behavioral.domain_adherence_violation",
                message=(
                    f"{len(out_of_scope)} tool calls touched paths outside the "
                    f"agent's owned scope ({owned_paths})."
                ),
                evidence={"transcript": transcript_path, "out_of_scope": out_of_scope[:8],
                          "owned_paths": owned_paths},
                fix="Either tighten the agent's `tools` whitelist, expand `owned_paths` "
                    "in the description, or stop the agent from working outside its scope.",
                source="https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents",
                produced_by="behavioral",
            ))

    # ----- self_correction_failure (≥3 identical consecutive calls) ----- #
    streak: list[tuple[int, str, str]] = []
    repeated_calls: list[tuple[str, str]] = []
    for _, name, params in tool_calls:
        sig = (name, json.dumps(params, sort_keys=True, default=str))
        if streak and streak[-1][1:] == sig:
            streak.append((len(streak) + 1, *sig))
            if len(streak) >= 3 and (sig[0], sig[1]) not in [(s[1], s[2]) for s in repeated_calls[:-1]]:
                repeated_calls.append((0, *sig))
        else:
            streak = [(1, *sig)]
    if any(len(streak) >= 3 for _ in [streak]) and len(streak) >= 3:
        findings.append(Finding(
            severity="warning",
            rule="behavioral.self_correction_failure",
            message=(
                f"Same tool call repeated {len(streak)} times consecutively without a "
                f"corrective change — agent did not self-correct on a wrong call."
            ),
            evidence={"transcript": transcript_path,
                      "tool": streak[-1][1], "repetitions": len(streak)},
            fix="When a tool call returns the wrong result or an error, change the next call. "
                "Repeating the same call rarely converges.",
            source="https://www.braintrust.dev/articles/ai-agent-evaluation-framework",
            produced_by="behavioral",
        ))

    # ----- error_silently_swallowed (tool_result is_error followed by silent claim) ----- #
    error_results = [tr for tr in tool_results if tr.get("is_error")]
    if error_results:
        # If we have any error tool_results AND text blocks AFTER them that
        # don't acknowledge an error/issue/fail/blocked, flag it.
        last_error_idx = max(events.index(tr) for tr in error_results if tr in events) if any(tr in events for tr in error_results) else -1
        post_error_text = " ".join(
            t for turn, t in text_blocks
            if turn > sum(1 for ev in events[:last_error_idx + 1] if ev.get("type") in ("turn", "message"))
        )
        if post_error_text and not re.search(
            r"\b(error|fail(ed)?|broken|blocked|cannot|could\s+not|unable)\b",
            post_error_text,
            re.IGNORECASE,
        ):
            findings.append(Finding(
                severity="warning",
                rule="behavioral.error_silently_swallowed",
                message=(
                    f"{len(error_results)} tool_result(s) returned errors, but the "
                    f"agent's subsequent text did not surface them."
                ),
                evidence={"transcript": transcript_path,
                          "error_result_count": len(error_results)},
                fix="Surface the error to the user explicitly. Do not pretend the call succeeded.",
                source="https://arxiv.org/html/2510.03999v3",
                produced_by="behavioral",
            ))

    # ----- output_format_drift (body promises sections; final response lacks them) ----- #
    body_sections = {m.group(1).lower() for m in _FORMAT_SECTION_RE.finditer(pf.body)}
    if body_sections and text_blocks:
        final_text = text_blocks[-1][1]
        final_sections = {m.group(1).lower() for m in _FORMAT_SECTION_RE.finditer(final_text)}
        missing = body_sections - final_sections
        if missing and len(body_sections) <= 4:
            findings.append(Finding(
                severity="suggestion",
                rule="behavioral.output_format_drift",
                message=(
                    "Agent body promises sections {body} but the final response "
                    "is missing {missing}.".format(body=sorted(body_sections),
                                                   missing=sorted(missing))
                ),
                evidence={"transcript": transcript_path, "missing_sections": sorted(missing)},
                fix="Either keep the promised section structure in responses, or "
                    "remove the section headings from the agent body if they're aspirational.",
                source="https://www.braintrust.dev/articles/ai-agent-evaluation-framework",
                produced_by="behavioral",
            ))

    # ----- instruction_following_gap (claim DETECTION; env-verification = v0.3) ----- #
    claims: list[tuple[int, str]] = []
    for turn, txt in text_blocks:
        for pat in _CLAIM_PATTERNS:
            for m in pat.finditer(txt):
                target = m.group(1) if m.groups() else m.group(0)
                claims.append((turn, target))
    if claims:
        findings.append(Finding(
            severity="suggestion",
            rule="behavioral.instruction_following_gap_claim_detected",
            message=(
                f"Agent made {len(claims)} verifiable claim(s) (e.g. 'I have updated X', "
                f"'Tests now pass'). v0.3 will verify these against env state; v0.2 only detects them."
            ),
            evidence={"transcript": transcript_path, "claims": claims[:8]},
            fix="Run `behavioral.instruction_following_gap` env-verification (v0.3) "
                "to confirm each claim against the environment.",
            source="https://arxiv.org/html/2601.03269",
            produced_by="behavioral",
        ))

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

    # Aggregate per-dimension scores.
    findings_by_dim = {d: [] for d in DIMENSIONS}
    _DIM_FOR_RULE = {
        "behavioral.tool_whitelist_violation":     "tool_hygiene",
        "behavioral.no_declared_tools":            "tool_hygiene",
        "behavioral.domain_adherence_violation":   "tool_hygiene",
        "behavioral.step_efficiency_exceeded":     "body_structure",
        "behavioral.self_correction_failure":      "body_structure",
        "behavioral.output_format_drift":          "body_structure",
        "behavioral.error_silently_swallowed":     "anti_patterns",
        "behavioral.instruction_following_gap_claim_detected": "anti_patterns",
    }
    for f in findings:
        if f.rule in _DIM_FOR_RULE:
            findings_by_dim[_DIM_FOR_RULE[f.rule]].append(f)
        elif f.rule.startswith("behavioral.tool_") or f.rule.startswith("behavioral.no_declared_tools"):
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
