#!/usr/bin/env python3
"""
runner.py — behavioral fixture runner. Phase 3 mode B.

Exercises an agent against canned prompts and grades the produced
transcript with replay.py + trajectory.py + a final-state assertions
check.

Two modes:

    Live mode (default):
        Invokes `claude -p <prompt> --agent <name>` for each fixture
        prompt and captures the transcript. Requires the Claude Code
        CLI on PATH and an authenticated session.

    Canned mode (--canned):
        Reads a pre-recorded transcript from `<fixture-dir>/canned/<n>.jsonl`
        instead of invoking the CLI. Used by CI and offline development
        so the runner is exercisable without billing tokens.

For each fixture the runner:
    1. Resolves the prompt (reads `prompts/<n>.md`).
    2. Gets the actual transcript (live or canned).
    3. Loads the expected trajectory (`expected/<n>.jsonl`).
    4. Loads the per-fixture assertions (`assertions.yaml`).
    5. Runs replay.py for the per-rule behavioral findings.
    6. Runs trajectory.match in the mode the assertions specify.
    7. Aggregates everything into a v1-schema report with `fixture_name`.

Assertions.yaml shape (one document; keys per fixture name):

    01-route-feature:
      match_mode: subset       # one of strict/unordered/subset/superset
      arg_keys: [path]         # optional; defaults to None (name-only)
      expected_outcome:        # optional; final-state assertions
        - kind: text_contains  # one of text_contains, text_not_contains
          value: "delegate"

    02-cross-service-plan:
      match_mode: unordered

Anti-goal: never run the live runner against production credentials.
Sandboxed env + fixtures only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import replay      # type: ignore
import trajectory  # type: ignore
from lint import SCHEMA_VERSION, _infer_kind, parse_file  # type: ignore


def parse_yaml_lite(text: str) -> dict:
    """Subset of YAML covering what assertions.yaml needs:
      - top-level keys (fixture names)
      - nested kv pairs (match_mode, arg_keys, expected_outcome)
      - inline lists [a, b, c]
      - block lists of mappings (- kind: x\\n  value: y)
    Avoids a pyyaml dependency.
    """
    out: dict = {}
    cur_top: Optional[str] = None
    cur_section: Optional[dict] = None
    cur_list_section: Optional[list] = None
    pending_list_item: Optional[dict] = None

    def flush_pending_item():
        nonlocal pending_list_item
        if pending_list_item is not None and cur_list_section is not None:
            cur_list_section.append(pending_list_item)
            pending_list_item = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        # Top-level key (no leading whitespace, ends with :)
        m_top = re.match(r"^([A-Za-z0-9_.-]+):\s*$", raw)
        if m_top:
            flush_pending_item()
            cur_top = m_top.group(1)
            cur_section = {}
            out[cur_top] = cur_section
            cur_list_section = None
            continue
        if cur_section is None:
            continue
        # 2-space indented key
        m_kv = re.match(r"^  ([A-Za-z0-9_.-]+):\s*(.*)$", raw)
        if m_kv:
            flush_pending_item()
            key, value = m_kv.group(1), m_kv.group(2).strip()
            if value == "":
                # Block list follows
                cur_list_section = []
                cur_section[key] = cur_list_section
                continue
            cur_section[key] = _coerce(value)
            cur_list_section = None
            continue
        # Block-list item: "    - kind: text_contains"
        m_li = re.match(r"^    -\s+([A-Za-z0-9_.-]+):\s*(.*)$", raw)
        if m_li and cur_list_section is not None:
            flush_pending_item()
            pending_list_item = {m_li.group(1): _coerce(m_li.group(2).strip())}
            continue
        # Continuation of pending item: "      key: value"
        m_cont = re.match(r"^      ([A-Za-z0-9_.-]+):\s*(.*)$", raw)
        if m_cont and pending_list_item is not None:
            pending_list_item[m_cont.group(1)] = _coerce(m_cont.group(2).strip())
            continue
    flush_pending_item()
    return out


def _coerce(v: str):
    s = v.strip()
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",")]
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


# --------------------------------------------------------------------------- #
# Live + canned runners
# --------------------------------------------------------------------------- #
def run_live(agent_name: str, prompt: str) -> list[dict]:
    """Invoke `claude -p` and capture stdout as a JSONL transcript."""
    cli = shutil.which("claude")
    if not cli:
        raise RuntimeError("`claude` CLI not on PATH; pass --canned or install Claude Code")
    r = subprocess.run(
        [cli, "-p", prompt, "--agent", agent_name, "--output-format", "stream-json"],
        capture_output=True, text=True, check=False, timeout=120,
    )
    # stream-json emits one event per line
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def run_canned(canned_path: Path) -> list[dict]:
    return [json.loads(line) for line in canned_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# --------------------------------------------------------------------------- #
# Fixture iteration
# --------------------------------------------------------------------------- #
def find_fixtures(fixture_dir: Path) -> list[str]:
    """Return fixture stem names (e.g. '01-route-feature') from prompts/."""
    p = fixture_dir / "prompts"
    if not p.is_dir():
        raise FileNotFoundError(f"missing prompts/ under {fixture_dir}")
    return sorted(f.stem for f in p.glob("*.md"))


def grade_fixture(
    agent_path: str,
    fixture_dir: Path,
    name: str,
    use_canned: bool,
    assertions: dict,
) -> dict:
    prompt = (fixture_dir / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    expected_path = fixture_dir / "expected" / f"{name}.jsonl"
    canned_path = fixture_dir / "canned" / f"{name}.jsonl"

    # --- get actual transcript ---
    if use_canned:
        events = run_canned(canned_path)
    else:
        agent_name = parse_file(agent_path).frontmatter.get("name") or Path(agent_path).stem
        events = run_live(str(agent_name), prompt)

    # write transcript to a tmp file so replay.py can ingest it
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tf:
        for ev in events:
            tf.write(json.dumps(ev) + "\n")
        transcript_path = tf.name

    try:
        report = replay.grade(agent_path, transcript_path)
    finally:
        os.unlink(transcript_path)

    # --- trajectory match ---
    fixture_assertions = assertions.get(name, {})
    match_mode = fixture_assertions.get("match_mode", "subset")
    arg_keys = fixture_assertions.get("arg_keys") or None
    if isinstance(arg_keys, str):
        arg_keys = [arg_keys]

    expected_calls = trajectory.load_expected_jsonl(str(expected_path)) if expected_path.is_file() else []
    actual_calls = [(name, params) for _turn, name, params in replay.collect_tool_calls(events)]
    traj_result = trajectory.match(match_mode, actual_calls, expected_calls, arg_keys)

    # --- final-state assertions (text_contains / text_not_contains) ---
    text_blocks = replay.collect_text_blocks(events)
    full_text = "\n".join(t for _, t in text_blocks)
    outcome_findings = []
    for assertion in fixture_assertions.get("expected_outcome", []) or []:
        kind = assertion.get("kind")
        value = assertion.get("value", "")
        if kind == "text_contains" and value not in full_text:
            outcome_findings.append({
                "severity": "warning",
                "rule": "behavioral.outcome_assertion_failed",
                "message": f"expected_outcome `text_contains: {value!r}` did not match.",
                "evidence": {"fixture": name, "assertion": assertion},
                "produced_by": "behavioral",
            })
        if kind == "text_not_contains" and value in full_text:
            outcome_findings.append({
                "severity": "warning",
                "rule": "behavioral.outcome_assertion_failed",
                "message": f"expected_outcome `text_not_contains: {value!r}` was matched.",
                "evidence": {"fixture": name, "assertion": assertion},
                "produced_by": "behavioral",
            })

    if not traj_result.matched:
        outcome_findings.append({
            "severity": "warning",
            "rule": "behavioral.trajectory_mismatch",
            "message": (
                f"trajectory match ({match_mode}) failed: "
                f"missing={[c[0] for c in traj_result.missing[:5]]} "
                f"extra={[c[0] for c in traj_result.extra[:5]]}"
            ),
            "evidence": {
                "fixture": name,
                "mode": match_mode,
                "actual_count": traj_result.actual_count,
                "expected_count": traj_result.expected_count,
                "missing": [{"name": n, "input": p} for n, p in traj_result.missing],
                "extra":   [{"name": n, "input": p} for n, p in traj_result.extra],
                "order_violations": traj_result.order_violations,
            },
            "produced_by": "behavioral",
        })

    # Merge outcome findings into the report.
    report["findings"].extend(outcome_findings)
    for f in outcome_findings:
        report["dimensions"]["body_structure"]["findings"].append(f)
    if outcome_findings:
        # Recompute body_structure score to reflect the new findings.
        from lint import score_for, Finding  # type: ignore
        existing = [Finding(**{k: v for k, v in f.items() if k in ("severity", "rule", "message")})
                    for f in report["dimensions"]["body_structure"]["findings"]]
        report["dimensions"]["body_structure"]["score"] = score_for(existing)

    # Augment behavioral_metadata
    report.setdefault("behavioral_metadata", {})
    report["behavioral_metadata"]["fixture_name"] = name
    report["behavioral_metadata"]["match_mode"] = match_mode
    report["behavioral_metadata"]["match_result"] = traj_result.matched
    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", required=True, help="Path to the agent .md file.")
    p.add_argument("--fixture-dir", required=True, help="Path to a behavior-fixtures/<archetype>/ directory.")
    p.add_argument("--canned", action="store_true",
                   help="Read transcripts from <fixture-dir>/canned/<n>.jsonl instead of invoking `claude`.")
    p.add_argument("--fixture", default=None,
                   help="Run a single fixture by stem name (e.g. 01-route-feature).")
    args = p.parse_args(argv)

    agent_path = args.agent
    fixture_dir = Path(args.fixture_dir).resolve()
    if not Path(agent_path).is_file():
        print(f"runner.py: agent not found: {agent_path}", file=sys.stderr)
        return 66
    if not fixture_dir.is_dir():
        print(f"runner.py: fixture dir not found: {fixture_dir}", file=sys.stderr)
        return 66

    assertions_path = fixture_dir / "assertions.yaml"
    assertions = parse_yaml_lite(assertions_path.read_text(encoding="utf-8")) if assertions_path.is_file() else {}

    fixtures = [args.fixture] if args.fixture else find_fixtures(fixture_dir)
    summary = []
    worst_rc = 0
    for name in fixtures:
        try:
            report = grade_fixture(agent_path, fixture_dir, name, use_canned=args.canned, assertions=assertions)
        except Exception as e:
            print(f"runner.py: {name}: {e}", file=sys.stderr)
            worst_rc = max(worst_rc, 2)
            continue
        verdict = report["overall"]["verdict"]
        match = report["behavioral_metadata"].get("match_result")
        summary.append({"fixture": name, "verdict": verdict, "match": match,
                        "score": report["overall"]["score"], "grade": report["overall"]["grade"]})
        rc = {"ship": 0, "revise": 1, "reject": 2}.get(verdict, 0)
        worst_rc = max(worst_rc, rc)

    print(json.dumps({
        "agent": str(agent_path),
        "fixture_dir": str(fixture_dir),
        "ran": len(summary),
        "summary": summary,
        "worst_verdict_exit": worst_rc,
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": SCHEMA_VERSION,
    }, indent=2))
    return worst_rc


if __name__ == "__main__":
    sys.exit(main())
