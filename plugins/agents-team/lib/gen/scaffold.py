#!/usr/bin/env python3
"""
scaffold.py — materialize a generated team into a target directory's .claude/.

Reads a `team.json` describing the team (orchestrator, specialists, skills,
rules, hooks), pulls templates from the plugin's `templates/`, renders them
via render.py, and writes the result to <target>/.claude/.

Then optionally runs the static linter on every produced agent + skill and
reports a summary (the generator's self-eval gate).

Usage:
    scaffold.py <team.json> --target <project-dir>
    scaffold.py <team.json> --target <project-dir> --no-self-eval
    scaffold.py <team.json> --target <project-dir> --dry-run

team.json shape (see schema below):

{
  "team_name": "E-Shop",
  "services": ["api", "web", "payments"],
  "primary_locale": "en",
  "orchestrator": {
    "archetype": "orchestrator",
    "values": { "name": "shop-orch", "description": "...", ... }
  },
  "agents": [
    { "archetype": "domain-engineer", "values": {...} },
    { "archetype": "qa-engineer",     "values": {...} },
    ...
  ],
  "skills": [
    { "archetype": "coordination-skill", "values": {...} }
  ],
  "rules": ["01-plan-first", "03-definition-of-done", "13-model-selection"],
  "hooks": ["notify", "session-init"],
  "settings_extras": {}
}
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent.parent
TEMPLATES = PLUGIN_ROOT / "templates"
sys.path.insert(0, str(HERE))
from render import render  # type: ignore


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] would write {path} ({len(content)} chars)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy(src: Path, dst: Path, dry_run: bool, replacements: dict | None = None) -> None:
    if dry_run:
        print(f"[dry-run] would copy {src} → {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if replacements:
        text = _read(src)
        text = render(text, replacements, tolerant=True)
        dst.write_text(text, encoding="utf-8")
        if src.suffix in (".sh",):
            os.chmod(dst, 0o755)
    else:
        shutil.copy2(src, dst)


def materialize(team_spec: dict, target_root: Path, dry_run: bool = False) -> dict:
    """Write the team into target_root/.claude/. Returns a manifest of created files."""
    claude_dir = target_root / ".claude"
    agents_dir = claude_dir / "agents"
    skills_dir = claude_dir / "skills"
    rules_dir = claude_dir / "rules"
    hooks_dir = claude_dir / "hooks"

    manifest: dict[str, list[str]] = {"agents": [], "skills": [], "rules": [], "hooks": [], "settings": []}

    team_name = team_spec.get("team_name", "Generated Team")

    # --- orchestrator ---
    orch = team_spec.get("orchestrator")
    if orch:
        out = _render_archetype("agents", orch["archetype"], orch.get("values", {}), team_spec)
        out_path = agents_dir / f"{orch['values']['name']}.md"
        _write(out_path, out, dry_run)
        manifest["agents"].append(str(out_path))

    # --- specialists ---
    for agent in team_spec.get("agents", []):
        out = _render_archetype("agents", agent["archetype"], agent.get("values", {}), team_spec)
        out_path = agents_dir / f"{agent['values']['name']}.md"
        _write(out_path, out, dry_run)
        manifest["agents"].append(str(out_path))

    # --- skills ---
    for skill in team_spec.get("skills", []):
        out = _render_archetype("skills", skill["archetype"], skill.get("values", {}), team_spec)
        skill_name = skill["values"]["name"]
        out_path = skills_dir / skill_name / "SKILL.md"
        _write(out_path, out, dry_run)
        manifest["skills"].append(str(out_path))

    # --- rules ---
    for rule_id in team_spec.get("rules", []):
        src = TEMPLATES / "rules" / f"{rule_id}.md"
        if not src.exists():
            print(f"scaffold.py: warning — rule template missing: {src}", file=sys.stderr)
            continue
        dst = rules_dir / f"{rule_id}.md"
        _copy(src, dst, dry_run, replacements={
            "services": ", ".join(team_spec.get("services", [])),
            "primary_locale": team_spec.get("primary_locale", "en"),
        })
        manifest["rules"].append(str(dst))

    # --- hooks ---
    for hook_id in team_spec.get("hooks", []):
        src = TEMPLATES / "hooks" / f"{hook_id}.sh"
        if not src.exists():
            print(f"scaffold.py: warning — hook template missing: {src}", file=sys.stderr)
            continue
        dst = hooks_dir / f"{hook_id}.sh"
        _copy(src, dst, dry_run, replacements={"TEAM_NAME": team_name})
        manifest["hooks"].append(str(dst))

    # --- settings.json ---
    if team_spec.get("hooks"):
        partial_path = TEMPLATES / "hooks" / "settings.json.partial"
        if partial_path.exists():
            partial = json.loads(_read(partial_path))
            partial.pop("_comment", None)
            settings_path = claude_dir / "settings.json"
            existing: dict = {}
            if settings_path.exists():
                try:
                    existing = json.loads(_read(settings_path))
                except json.JSONDecodeError:
                    print("scaffold.py: existing settings.json is not valid JSON; skipping merge",
                          file=sys.stderr)
            merged = _merge_dict(existing, partial)
            extras = team_spec.get("settings_extras") or {}
            if extras:
                merged = _merge_dict(merged, extras)
            _write(settings_path, json.dumps(merged, indent=2) + "\n", dry_run)
            manifest["settings"].append(str(settings_path))

    return manifest


def _merge_dict(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _render_archetype(kind: str, archetype: str, values: dict, team_spec: dict) -> str:
    src = TEMPLATES / kind / f"{archetype}.md.template"
    if not src.exists():
        raise FileNotFoundError(f"archetype template missing: {src}")
    template = _read(src)
    merged = {
        "team_name": team_spec.get("team_name", "Team"),
        "services": ", ".join(team_spec.get("services", [])),
        "primary_locale": team_spec.get("primary_locale", "en"),
        "color": "#5B8DEF",
        **values,
    }
    return render(template, merged, tolerant=True)


# Grade ordering (lower index = better). The min-grade gate fails when any
# produced agent's grade index exceeds the floor's index.
_GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
EXIT_GRADE_FLOOR_VIOLATED = 3


def self_eval(manifest: dict, min_grade: str = "B") -> int:
    """Run the static linter on every produced agent + skill. Returns the
    worst exit code observed:
      0 = all ship + all at-or-above the min-grade floor
      1 = at least one revise verdict from the linter
      2 = at least one reject verdict from the linter
      3 = grades above floor exist but no revise/reject verdicts
    Min-grade always wins over verdict — i.e., a `ship` with a `C` grade
    when floor is `B` returns 3.
    """
    if min_grade not in _GRADE_ORDER:
        raise ValueError(f"min_grade must be one of {list(_GRADE_ORDER)}")
    floor = _GRADE_ORDER[min_grade]
    lint_py = PLUGIN_ROOT / "lib" / "eval" / "lint.py"
    worst = 0
    grade_violations: list[tuple[str, str]] = []

    print("\n=== Self-evaluation ===")
    for path in manifest["agents"] + manifest["skills"]:
        try:
            r = subprocess.run(
                [sys.executable, str(lint_py), path],
                capture_output=True, text=True, check=False,
            )
            if r.returncode > worst:
                worst = r.returncode
            try:
                report = json.loads(r.stdout)
                ov = report["overall"]
                grade = ov["grade"]
                if _GRADE_ORDER[grade] > floor:
                    grade_violations.append((path, grade))
                marker = "" if _GRADE_ORDER[grade] <= floor else "  <-- below floor"
                print(f"  {os.path.basename(path):40s} {grade}  {ov['score']:3d}/100  {ov['verdict']}{marker}")
            except (json.JSONDecodeError, KeyError):
                print(f"  {os.path.basename(path):40s} ! could not parse lint output")
        except OSError as e:
            print(f"  {os.path.basename(path)}: lint failed: {e}")

    if grade_violations and worst < EXIT_GRADE_FLOOR_VIOLATED:
        worst = EXIT_GRADE_FLOOR_VIOLATED
        names = ", ".join(f"{os.path.basename(p)} ({g})" for p, g in grade_violations)
        print(f"\n!! Min-grade gate ({min_grade}) violated by: {names}")

    print(f"=== Self-eval worst verdict: exit {worst} (min-grade={min_grade}) ===")
    return worst


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("team", help="Path to team.json")
    p.add_argument("--target", required=True, help="Project root (where .claude/ will live)")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    p.add_argument("--no-self-eval", action="store_true",
                   help="Skip the static linter on produced files. "
                        "Requires AGENTS_TEAM_DEV=1 in the environment — the gate "
                        "exists to catch the mistakes you'll make at 2am, do not "
                        "skip it for production runs.")
    p.add_argument("--min-grade", choices=tuple(_GRADE_ORDER), default="B",
                   help="Lowest acceptable grade per produced agent (default: B). "
                        "Any agent below this floor exits with code 3 even if no "
                        "agent triggered a revise/reject verdict.")
    args = p.parse_args(argv)

    if args.no_self_eval and os.environ.get("AGENTS_TEAM_DEV") != "1":
        print(
            "scaffold.py: --no-self-eval requires AGENTS_TEAM_DEV=1 "
            "(development mode). Self-eval is the gate; do not skip it for "
            "production runs.",
            file=sys.stderr,
        )
        return 64

    if not os.path.isfile(args.team):
        print(f"scaffold.py: team spec not found: {args.team}", file=sys.stderr)
        return 66
    target_root = Path(args.target).resolve()
    if not target_root.exists():
        print(f"scaffold.py: target not found: {target_root}", file=sys.stderr)
        return 66

    spec = json.loads(Path(args.team).read_text(encoding="utf-8"))
    manifest = materialize(spec, target_root, dry_run=args.dry_run)

    print(f"\nGenerated team for {spec.get('team_name', 'team')} at {target_root / '.claude'}")
    for kind, paths in manifest.items():
        if paths:
            print(f"  {kind}: {len(paths)}")

    if args.dry_run or args.no_self_eval:
        return 0
    return self_eval(manifest, min_grade=args.min_grade)


if __name__ == "__main__":
    sys.exit(main())
