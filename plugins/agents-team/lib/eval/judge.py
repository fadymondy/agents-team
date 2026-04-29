#!/usr/bin/env python3
"""
judge.py — Phase 2 of the agents-team evaluator: LLM-as-judge skeleton.

Given an agent or skill file and the canonical rubric, build per-dimension
judge prompts (one isolated call per dimension) and emit a v1-schema report.

Judge model is swappable via ANTHROPIC_JUDGE_MODEL env var (default: claude-sonnet-4-6).
Cache key: sha256(file_contents) + judge_model + rubric_version. Cached results
are reused unless --no-cache is passed.

Status: v0.1 SKELETON. Real model calls are wired through the
`call_judge()` adapter; the adapter falls back to a "dry-run" mode that
emits the prompts without invoking the model. To run live, set:
  ANTHROPIC_API_KEY    — required
  ANTHROPIC_JUDGE_MODEL — optional, defaults to claude-sonnet-4-6

Dry-run mode is useful for inspecting prompts and for CI on PRs that don't
need a live API call.

Usage:
    judge.py <path>                 # judge with default model
    judge.py --dry-run <path>       # emit prompts, no API call
    judge.py --model haiku <path>   # override model
    judge.py --no-cache <path>      # skip cache lookup
    judge.py --rubric path.md <p>   # alternate rubric file
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Reuse parsing + scoring infrastructure from the static linter.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lint import (  # type: ignore
    DIMENSIONS,
    DIMENSION_WEIGHTS_AGENT,
    DIMENSION_WEIGHTS_SKILL,
    SCHEMA_VERSION,
    grade_for,
    parse_file,
    score_for,
    verdict_for,
    Finding,
    _infer_kind,
)


DEFAULT_RUBRIC_PATH = HERE / "rubric.md"
DEFAULT_MODEL = os.environ.get("ANTHROPIC_JUDGE_MODEL", "claude-sonnet-4-6")
RUBRIC_VERSION_RE = re.compile(r"\*\*Rubric version:\*\*\s*`([^`]+)`")


def parse_rubric(path: Path) -> tuple[str, dict[str, list[dict[str, str]]]]:
    """
    Parse the canonical rubric.md into per-dimension rule lists.

    Returns (rubric_version, {dimension: [rule_dict, ...]}).
    Each rule_dict has: rule_id, severity, phase, prompt, source.
    """
    text = path.read_text(encoding="utf-8")
    m = RUBRIC_VERSION_RE.search(text)
    rubric_version = m.group(1) if m else "unknown"

    rules: dict[str, list[dict[str, str]]] = {d: [] for d in DIMENSIONS}
    current_dim: Optional[str] = None
    in_table = False

    for line in text.splitlines():
        # Section header for a dimension table
        m = re.match(r"^## Dimension: `([a-z_]+)`", line)
        if m:
            current_dim = m.group(1) if m.group(1) in DIMENSIONS else None
            in_table = False
            continue
        if not current_dim:
            continue

        # Detect the start of a table by its separator (--- |)
        if re.match(r"^\|[-: |]+\|\s*$", line):
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            rule_id_raw = cells[0]
            severity = cells[1]
            phase = cells[2]
            prompt = cells[3]

            # rule_id wrapped in backticks
            rid = rule_id_raw.strip("`").strip()
            if not rid or " " in rid:
                continue
            rules[current_dim].append({
                "rule_id": rid,
                "severity": severity,
                "phase": phase,
                "prompt": prompt,
            })
        elif in_table and not line.startswith("|"):
            in_table = False

    return rubric_version, rules


def filter_judge_rules(rules_for_dim: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only rules whose phase column mentions 'judge'."""
    return [r for r in rules_for_dim if "judge" in r["phase"].lower()]


def build_dimension_prompt(
    dimension: str,
    rules: list[dict[str, str]],
    file_path: str,
    file_text: str,
    kind: str,
) -> str:
    """Build the judge prompt for a single dimension. Evidence-before-score."""
    bulleted = "\n".join(
        f"- `{r['rule_id']}` ({r['severity']}): {r['prompt']}" for r in rules
    )
    return f"""You are evaluating one dimension of a Claude Code {kind} file.

DIMENSION: {dimension}
FILE: {file_path}

The file contents are between <file> tags below.

For each rule listed, do this in order:
1. Quote the file. Cite the exact text or `<no-evidence>` if absent.
2. Decide: pass / fail / n/a.
3. If fail, write a one-line `fix` suggestion.

After processing every rule, return a single JSON object on its own line:

{{
  "dimension": "{dimension}",
  "score": <integer 0-100, lower for more/severe failures>,
  "findings": [
    {{ "rule": "<rule_id>", "severity": "critical|warning|suggestion",
       "message": "<why>", "evidence": {{ "quote": "<quoted text or empty>" }},
       "fix": "<one-liner>" }}
  ]
}}

DO NOT bundle dimensions. DO NOT propose rules outside the list.
DO NOT score before quoting evidence — that is a calibration failure.

RULES:
{bulleted}

<file>
{file_text}
</file>
"""


# --------------------------------------------------------------------------- #
# Judge adapter
# --------------------------------------------------------------------------- #
def call_judge(prompt: str, model: str, dry_run: bool) -> dict[str, Any]:
    """
    Single judge call for one dimension. Returns the parsed JSON the judge
    emits at the end of its response. In dry-run mode, returns a stub
    indicating the prompt was built (not sent).

    To wire a live call, fill in the `_call_anthropic()` function below.
    """
    if dry_run:
        return {
            "score": 100,
            "findings": [],
            "_dry_run": True,
            "_prompt_chars": len(prompt),
        }

    try:
        return _call_anthropic(prompt, model)
    except _NoAnthropicSDK:
        # Fall back to dry-run with a clear note so the report tells the user.
        return {
            "score": 100,
            "findings": [{
                "rule": "judge.skipped_no_sdk",
                "severity": "suggestion",
                "message": (
                    "Anthropic SDK not installed; judge dimension skipped. "
                    "Install `anthropic` and set ANTHROPIC_API_KEY to enable Phase 2."
                ),
            }],
            "_dry_run": True,
        }


class _NoAnthropicSDK(RuntimeError):
    pass


def _call_anthropic(prompt: str, model: str) -> dict[str, Any]:
    """Live judge call. Imports the SDK lazily so dry-run works without it."""
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError as e:
        raise _NoAnthropicSDK from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise _NoAnthropicSDK("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(part.text for part in msg.content if hasattr(part, "text"))
    # Pick out the last JSON object in the response.
    json_blob = _extract_last_json(text)
    if json_blob is None:
        return {"score": 50, "findings": [{
            "rule": "judge.unparseable_response",
            "severity": "warning",
            "message": "Judge response did not contain a parseable JSON object.",
        }]}
    return json_blob


_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_last_json(text: str) -> Optional[dict[str, Any]]:
    # Walk balanced braces from the end.
    depth = 0
    end = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] == "}":
            if end == -1:
                end = i
            depth += 1
        elif text[i] == "{":
            depth -= 1
            if depth == 0 and end != -1:
                try:
                    return json.loads(text[i:end + 1])
                except json.JSONDecodeError:
                    end = -1
    return None


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def cache_dir() -> Path:
    base = os.environ.get("AGENTS_TEAM_CACHE") or os.path.expanduser("~/.cache/agents-team/judge")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_key(file_text: str, model: str, rubric_version: str) -> str:
    h = hashlib.sha256()
    h.update(file_text.encode("utf-8"))
    h.update(b"\0")
    h.update(model.encode("utf-8"))
    h.update(b"\0")
    h.update(rubric_version.encode("utf-8"))
    return h.hexdigest()


def cache_get(key: str) -> Optional[dict[str, Any]]:
    p = cache_dir() / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def cache_put(key: str, report: dict[str, Any]) -> None:
    p = cache_dir() / f"{key}.json"
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def judge_file(
    path: str,
    rubric_path: Path = DEFAULT_RUBRIC_PATH,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    use_cache: bool = True,
    kind: Optional[str] = None,
) -> dict[str, Any]:
    pf = parse_file(path)
    if kind is None:
        kind = _infer_kind(path, pf.frontmatter)
    weights = DIMENSION_WEIGHTS_AGENT if kind == "agent" else DIMENSION_WEIGHTS_SKILL

    rubric_version, rules_by_dim = parse_rubric(rubric_path)

    raw_text = pf.raw
    ck = cache_key(raw_text, model, rubric_version)
    if use_cache and not dry_run:
        cached = cache_get(ck)
        if cached:
            return cached

    dimensions_out: dict[str, dict[str, Any]] = {}
    all_findings: list[dict[str, Any]] = []

    for dim in DIMENSIONS:
        judge_rules = filter_judge_rules(rules_by_dim.get(dim, []))
        if not judge_rules:
            # No judge rules for this dimension — the static linter handled it.
            dimensions_out[dim] = {
                "score": 100,
                "weight": weights[dim],
                "findings": [],
            }
            continue

        prompt = build_dimension_prompt(dim, judge_rules, path, raw_text, kind)
        result = call_judge(prompt, model, dry_run=dry_run)
        score = int(result.get("score", 50))
        findings = []
        for f in result.get("findings", []):
            f.setdefault("produced_by", "judge")
            findings.append(f)
        dimensions_out[dim] = {
            "score": max(0, min(100, score)),
            "weight": weights[dim],
            "findings": findings,
        }
        all_findings.extend(findings)

    overall_score = round(sum(d["score"] * d["weight"] for d in dimensions_out.values()))
    finding_objs = [Finding(
        severity=f.get("severity", "suggestion"),
        rule=f.get("rule", "judge.unknown"),
        message=f.get("message", ""),
    ) for f in all_findings]
    overall_grade = grade_for(overall_score)
    overall_verdict = verdict_for(overall_score, finding_objs)

    report = {
        "agent": pf.frontmatter.get("name") or os.path.splitext(os.path.basename(path))[0],
        "path": path,
        "kind": kind,
        "overall": {
            "score": overall_score,
            "grade": overall_grade,
            "verdict": overall_verdict,
        },
        "dimensions": dimensions_out,
        "findings": sorted(
            all_findings,
            key=lambda f: ("critical", "warning", "suggestion").index(f.get("severity", "suggestion")),
        ),
        "produced_by": "judge",
        "judge_model": model,
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": SCHEMA_VERSION,
        "rubric_version": rubric_version,
    }

    if use_cache and not dry_run:
        cache_put(ck, report)
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", nargs="?")
    p.add_argument("--dry-run", action="store_true",
                   help="Build prompts but don't call the judge model.")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Judge model (default: {DEFAULT_MODEL}).")
    p.add_argument("--no-cache", action="store_true",
                   help="Skip the file-hash + model cache.")
    p.add_argument("--rubric", default=str(DEFAULT_RUBRIC_PATH),
                   help="Path to the rubric markdown file.")
    p.add_argument("--kind", choices=("agent", "skill"), default=None)
    p.add_argument("--print-prompts", action="store_true",
                   help="Print each dimension's prompt to stderr (debug).")
    args = p.parse_args(argv)

    if not args.path:
        p.print_help(sys.stderr)
        return 64
    if not os.path.isfile(args.path):
        print(f"judge.py: not a file: {args.path}", file=sys.stderr)
        return 66

    rubric = Path(args.rubric)
    if not rubric.is_file():
        print(f"judge.py: rubric not found: {rubric}", file=sys.stderr)
        return 66

    report = judge_file(
        args.path,
        rubric_path=rubric,
        model=args.model,
        dry_run=args.dry_run,
        use_cache=not args.no_cache,
        kind=args.kind,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")

    return {"ship": 0, "revise": 1, "reject": 2}.get(report["overall"]["verdict"], 0)


if __name__ == "__main__":
    sys.exit(main())
