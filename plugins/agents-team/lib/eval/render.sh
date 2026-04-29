#!/usr/bin/env bash
# render.sh — turn a v1 evaluator report (JSON) into a Markdown report.
#
# Usage:
#   render.sh <report.json>
#   cat report.json | render.sh -
#
# Exit codes (only when --ci is passed via env or wrapper, see lint.sh):
#   0 on overall.verdict == "ship"
#   1 on "revise"
#   2 on "reject"
#
# Requires: jq.

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "render.sh: jq is required (brew install jq)" >&2
  exit 127
fi

input="${1:-}"
if [[ -z "$input" ]]; then
  echo "Usage: render.sh <report.json|-> " >&2
  exit 64
fi

if [[ "$input" == "-" ]]; then
  json="$(cat)"
else
  if [[ ! -f "$input" ]]; then
    echo "render.sh: file not found: $input" >&2
    exit 66
  fi
  json="$(cat "$input")"
fi

agent="$(jq -r '.agent'                      <<<"$json")"
path="$(jq -r  '.path'                       <<<"$json")"
kind="$(jq -r  '.kind // "agent"'            <<<"$json")"
score="$(jq -r '.overall.score'              <<<"$json")"
grade="$(jq -r '.overall.grade'              <<<"$json")"
verdict="$(jq -r '.overall.verdict'          <<<"$json")"
produced_by="$(jq -r '.produced_by // "static"' <<<"$json")"
produced_at="$(jq -r '.produced_at // ""'    <<<"$json")"
judge_model="$(jq -r '.judge_model // ""'    <<<"$json")"

emoji=""
case "$verdict" in
  ship)    emoji="✅" ;;
  revise)  emoji="⚠️"  ;;
  reject)  emoji="❌" ;;
esac

cat <<EOF
# $agent

$emoji **Verdict: $verdict** — Grade $grade ($score/100)

- **Path:** \`$path\`
- **Kind:** $kind
- **Produced by:** $produced_by${judge_model:+ ($judge_model)}
${produced_at:+- **At:** $produced_at}

## Dimensions

| Dimension       | Score | Weight |
|-----------------|------:|-------:|
EOF

for dim in frontmatter description tool_hygiene model_fit body_structure anti_patterns; do
  ds="$(jq -r ".dimensions.$dim.score"  <<<"$json")"
  dw="$(jq -r ".dimensions.$dim.weight" <<<"$json")"
  printf "| %-15s | %5s | %6s |\n" "$dim" "$ds" "$dw"
done

echo

# Findings — render each severity bucket if non-empty.
for sev in critical warning suggestion; do
  count="$(jq --arg s "$sev" '[.findings[] | select(.severity == $s)] | length' <<<"$json")"
  if [[ "$count" -eq 0 ]]; then
    continue
  fi

  case "$sev" in
    critical)   header="## Critical findings ($count)" ;;
    warning)    header="## Warnings ($count)" ;;
    suggestion) header="## Suggestions ($count)" ;;
  esac
  echo "$header"
  echo

  jq -r --arg s "$sev" '
    .findings[] | select(.severity == $s) |
    "- **`" + .rule + "`** — " + .message
    + (if .evidence then "\n  - Evidence: `" + (.evidence | tostring) + "`" else "" end)
    + (if .fix      then "\n  - Fix: " + .fix else "" end)
    + (if .source   then "\n  - Source: " + .source else "" end)
  ' <<<"$json"
  echo
done

# Footer / one-liner suitable for log scraping.
nc="$(jq '[.findings[] | select(.severity == "critical")]   | length' <<<"$json")"
nw="$(jq '[.findings[] | select(.severity == "warning")]    | length' <<<"$json")"
ns="$(jq '[.findings[] | select(.severity == "suggestion")] | length' <<<"$json")"

echo "---"
echo "_$agent: $grade ($score/100) — $nc critical, $nw warnings, $ns suggestions_"
