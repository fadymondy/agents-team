#!/usr/bin/env bash
# lint.sh — entry point for the static linter.
#
# Wraps lint.py (JSON) + render.sh (Markdown). Writes both to
# .claude/agent-quality/<agent>.{json,md} by default; with --stdout, emits
# the Markdown report to stdout (and JSON suppressed).
#
# Usage:
#   lint.sh <path-to-agent-or-skill>          # default: write to .claude/agent-quality/
#   lint.sh --stdout <path>                   # print Markdown to stdout
#   lint.sh --json   <path>                   # print JSON to stdout
#   lint.sh --ci     <path>                   # CI mode: exit nonzero on revise/reject
#   lint.sh --strict <path>                   # promote suggestion → warning
#
# Exit codes:
#   0 = ship  ;  1 = revise  ;  2 = reject  ;  64 = bad CLI  ;  66 = file not found
#
# Requires: python3 (stdlib only), jq.

set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON_BIN:-python3}"

ci=0
strict=0
deep=0
mode="files"   # files | stdout-md | stdout-json

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stdout) mode="stdout-md"; shift ;;
    --json)   mode="stdout-json"; shift ;;
    --ci)     ci=1; shift ;;
    --strict) strict=1; shift ;;
    --deep)   deep=1; shift ;;
    -h|--help)
      sed -n 's/^# //p' "$0" | head -n 22
      exit 0
      ;;
    --) shift; break ;;
    -*)
      echo "lint.sh: unknown flag: $1" >&2
      exit 64
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 1 ]]; then
  echo "Usage: lint.sh [--stdout|--json] [--ci] [--strict] <path-to-agent-or-skill>" >&2
  exit 64
fi

target="$1"
if [[ ! -f "$target" ]]; then
  echo "lint.sh: not a file: $target" >&2
  exit 66
fi

# Run the static linter. Capture stdout (JSON) and python exit code.
strict_arg=()
[[ "$strict" -eq 1 ]] && strict_arg=(--strict)

set +e
json_out="$("$PYTHON" "$HERE/lint.py" "${strict_arg[@]}" "$target")"
py_rc=$?
set -e

# --deep: chain to the LLM-as-judge (Phase 2). Merge its findings into
# the static report so consumers see one combined view.
if [[ "$deep" -eq 1 ]]; then
  set +e
  judge_out="$("$PYTHON" "$HERE/judge.py" "$target")"
  judge_rc=$?
  set -e
  if [[ -n "$judge_out" ]]; then
    json_out="$(jq -n \
      --argjson static "$json_out" \
      --argjson judge  "$judge_out" \
      '$static
       | .findings = ($static.findings + ($judge.findings // []))
       | .dimensions = (
           .dimensions
           | to_entries
           | map(
               . as $e
               | .value.findings = (.value.findings + (($judge.dimensions[$e.key].findings) // []))
               | .
             )
           | from_entries
         )
       | .judge_model = ($judge.judge_model // null)
       | .rubric_version = ($judge.rubric_version // null)
       | .produced_by = "static+judge"')"
    # Take the more severe of the two verdicts.
    if [[ "$judge_rc" -gt "$py_rc" ]]; then py_rc="$judge_rc"; fi
  fi
fi

case "$mode" in
  stdout-json)
    printf '%s\n' "$json_out"
    exit $(( ci ? py_rc : 0 ))
    ;;
  stdout-md)
    printf '%s' "$json_out" | "$HERE/render.sh" -
    exit $(( ci ? py_rc : 0 ))
    ;;
  files)
    # Resolve project root: prefer git, fall back to CWD.
    if root="$(git -C "$(dirname "$target")" rev-parse --show-toplevel 2>/dev/null)"; then
      :
    else
      root="$(pwd)"
    fi
    out_dir="$root/.claude/agent-quality"
    mkdir -p "$out_dir"
    name="$(printf '%s' "$json_out" | jq -r '.agent')"
    json_path="$out_dir/$name.json"
    md_path="$out_dir/$name.md"
    printf '%s\n' "$json_out" > "$json_path"
    printf '%s' "$json_out" | "$HERE/render.sh" - > "$md_path"

    # Print the one-liner summary to stdout for log scraping.
    score="$(jq -r '.overall.score'   <<<"$json_out")"
    grade="$(jq -r '.overall.grade'   <<<"$json_out")"
    nc="$(jq '[.findings[] | select(.severity=="critical")]   | length' <<<"$json_out")"
    nw="$(jq '[.findings[] | select(.severity=="warning")]    | length' <<<"$json_out")"
    ns="$(jq '[.findings[] | select(.severity=="suggestion")] | length' <<<"$json_out")"
    echo "$name: $grade ($score/100) — $nc critical, $nw warnings, $ns suggestions [$json_path]"
    exit $(( ci ? py_rc : 0 ))
    ;;
esac
