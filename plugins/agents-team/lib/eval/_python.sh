# shellcheck shell=bash
# _python.sh — pick a working Python 3 interpreter. Source it, then use
# "${PYTHON[@]}" (an array, because `py -3` is two words).
#
# Order: $PYTHON_BIN if set, else `python3` if `python3 -c 1` runs, else
# `python`, else `py -3`. On Windows `python3` is often the Microsoft Store
# alias, which exists on PATH but exits non-zero without running anything.

# shellcheck disable=SC2034  # PYTHON is consumed by the sourcing script
pick_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    # shellcheck disable=SC2206  # word-split on purpose: PYTHON_BIN="py -3"
    PYTHON=($PYTHON_BIN)
    return 0
  fi
  local candidate
  for candidate in "python3" "python" "py -3"; do
    # shellcheck disable=SC2086  # word-split on purpose for "py -3"
    if $candidate -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
      # shellcheck disable=SC2206
      PYTHON=($candidate)
      return 0
    fi
  done
  echo "No working Python 3 found (tried python3, python, py -3). Install Python 3 or set PYTHON_BIN." >&2
  return 1
}
