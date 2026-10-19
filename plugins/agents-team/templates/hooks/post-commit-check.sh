#!/usr/bin/env bash
# post-commit-check.sh — stub for project-specific post-commit guards.
#
# Claude Code has no PostCommit hook event, so this is wired in
# `.claude/settings.json` as a PostToolUse hook with matcher "Bash". It exits
# immediately unless the Bash command that just ran was a `git commit`.
# Examples of what you might add:
#   - reject commits that include secrets (use git-secrets / trufflehog)
#   - reject commits that touch CI files without a matching label
#   - reject commits that bypass a lint/typecheck pre-commit hook
#
# Exit 2 + a message on stderr feeds the message back to Claude.
#
# This template is intentionally empty so generated teams ship a wired hook
# they can fill in without modifying settings.json.

set -u

input=$(cat)

if command -v jq >/dev/null 2>&1; then
  command_run=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  # No jq (common on Windows Git Bash): crude match on the raw payload.
  command_run="$input"
fi

# Not a commit → nothing to check.
if ! printf '%s' "$command_run" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+commit\b'; then
  exit 0
fi

# >>> Add your checks here.
# Example skeleton:
#
#   message=$(git log -1 --pretty=%B)
#   if echo "$message" | grep -qiE '(BEGIN PRIVATE KEY|sk_live_|aws_access_key_id)'; then
#     echo "post-commit-check: secret-like content in last commit message" >&2
#     exit 2
#   fi
# <<<

exit 0
