#!/usr/bin/env bash
# calibrate.sh — measure judge.py vs hand-graded calibration fixtures.
#
# Iterates every <name>.md / <name>.expected.json pair under
# lib/eval/calibration/, runs the judge with --no-cache, and prints a
# per-dimension Spearman correlation table.
#
# Pass thresholds (Galileo 2026):
#   ≥0.80  calibrated (target)
#   ≥0.75  acceptable (CI floor)
#   <0.75  blocks the rubric change
#
# Usage:
#   calibrate.sh                 # full run (live judge)
#   calibrate.sh --static        # use static linter scores (no API needed)
#   calibrate.sh --threshold 0.7 # custom CI floor
#
# Without ANTHROPIC_API_KEY, the judge runs in dry-run mode and emits
# uniform 100s — which gives an artificial perfect Spearman. The script
# detects this and exits with a clear notice instead of a misleading pass.

set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON_BIN:-python3}"
CAL_DIR="$HERE/calibration"

mode="judge"
threshold="0.75"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --static)    mode="static"; shift ;;
    --threshold) threshold="$2"; shift 2 ;;
    -h|--help)
      sed -n 's/^# //p' "$0" | head -n 20
      exit 0
      ;;
    *)
      echo "calibrate.sh: unknown arg: $1" >&2
      exit 64
      ;;
  esac
done

if [[ ! -d "$CAL_DIR" ]]; then
  echo "calibrate.sh: no calibration directory at $CAL_DIR" >&2
  exit 66
fi

# Detect the dry-run trap before doing real work.
if [[ "$mode" == "judge" ]]; then
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "calibrate.sh: ANTHROPIC_API_KEY not set — judge would run in" >&2
    echo "  dry-run mode (uniform 100 scores) and report a meaningless" >&2
    echo "  Spearman of 1.0. Either set the key for a real run or pass" >&2
    echo "  --static to compare the static linter against the human grades." >&2
    exit 65
  fi
fi

dimensions=(frontmatter description tool_hygiene model_fit body_structure anti_patterns overall)
tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT
mkdir -p "$tmp_root"

# Per-dimension TSV files (judge_score \t human_score). Cleared on each run.
for dim in "${dimensions[@]}"; do : > "$tmp_root/$dim.tsv"; done

n=0
for fixture in "$CAL_DIR"/*.md; do
  [[ -f "$fixture" ]] || continue
  name="$(basename "$fixture" .md)"
  expected="$CAL_DIR/$name.expected.json"
  if [[ ! -f "$expected" ]]; then
    echo "calibrate.sh: missing expected.json for $name; skipping" >&2
    continue
  fi
  n=$((n + 1))

  # lint.py / judge.py exit 1 or 2 on revise/reject — that is a verdict,
  # not a calibrate failure. Keep stdout, drop the exit code.
  set +e
  if [[ "$mode" == "judge" ]]; then
    actual_json="$("$PYTHON" "$HERE/judge.py" --no-cache "$fixture")"
  else
    actual_json="$("$PYTHON" "$HERE/lint.py" "$fixture")"
  fi
  set -e
  expected_json="$(cat "$expected")"

  for dim in "${dimensions[@]}"; do
    if [[ "$dim" == "overall" ]]; then
      a=$(echo "$actual_json"  | "$PYTHON" -c "import json,sys; print(json.load(sys.stdin)['overall']['score'])")
      h=$(echo "$expected_json"| "$PYTHON" -c "import json,sys; print(json.load(sys.stdin)['overall']['score'])")
    else
      a=$(echo "$actual_json"  | "$PYTHON" -c "import json,sys; print(json.load(sys.stdin)['dimensions']['$dim']['score'])")
      h=$(echo "$expected_json"| "$PYTHON" -c "import json,sys; print(json.load(sys.stdin)['dimensions']['$dim']['score'])")
    fi
    printf '%s\t%s\n' "$a" "$h" >> "$tmp_root/$dim.tsv"
  done
done

if [[ "$n" -lt 2 ]]; then
  echo "calibrate.sh: need at least 2 calibration pairs (have $n)" >&2
  exit 65
fi

echo
printf 'Calibration: mode=%s n=%d threshold=%s\n' "$mode" "$n" "$threshold"
printf '%-18s %8s %s\n' "dimension" "spearman" "status"
echo "------------------------------------------------------"

worst=1.0
fail=0
for dim in "${dimensions[@]}"; do
  rho="$("$PYTHON" "$HERE/spearman.py" "$tmp_root/$dim.tsv")"
  status="—"
  if [[ "$rho" == "nan" ]]; then
    status="n/a"
  else
    cmp=$(awk -v a="$rho" -v t="$threshold" 'BEGIN { print (a < t ? "fail" : (a < 0.80 ? "ok" : "pass")) }')
    status="$cmp"
    if [[ "$cmp" == "fail" ]]; then fail=1; fi
    # track worst numeric rho
    worst=$(awk -v a="$rho" -v w="$worst" 'BEGIN { print (a < w ? a : w) }')
  fi
  printf '%-18s %8s %s\n' "$dim" "$rho" "$status"
done

echo "------------------------------------------------------"
printf 'Worst dimension Spearman: %s (threshold %s)\n' "$worst" "$threshold"

if [[ "$fail" -eq 1 ]]; then
  echo "calibrate.sh: at least one dimension is below the threshold." >&2
  exit 1
fi
exit 0
