#!/usr/bin/env python3
"""
trajectory.py — LangChain-style trajectory matching for behavioral evals.

Compares an actual tool-call sequence against an expected one in one of
four modes:

    strict     — same names, same order, AND tool args match.
    unordered  — same names, any order; arg-matching keys honored per call.
    subset     — actual ⊆ expected (every actual call appears in expected).
    superset   — actual ⊇ expected (every expected call appears in actual).

Each call is compared by name + a configurable set of input keys ("arg
keys"). If `arg_keys` is None, only the tool name is compared. If
`arg_keys` is a list, those keys' values must match exactly. This mirrors
`agentevals` (https://github.com/langchain-ai/agentevals).

Calls have shape (name: str, params: dict). The expected sequence is a
list of these tuples loaded from a fixture's expected/<n>.jsonl.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


Call = tuple[str, dict]
MATCH_MODES = ("strict", "unordered", "subset", "superset")


@dataclass
class MatchResult:
    matched: bool
    mode: str
    actual_count: int
    expected_count: int
    missing: list[Call]      # in expected, not in actual (subset/strict)
    extra: list[Call]        # in actual, not in expected (superset/strict)
    order_violations: list[tuple[int, str, str]] = None  # (idx, expected, actual) for strict


# --------------------------------------------------------------------------- #
# Comparison helpers
# --------------------------------------------------------------------------- #
def _key_for(call: Call, arg_keys: Optional[list[str]]) -> tuple:
    name, params = call
    if not arg_keys:
        return (name,)
    bits = [name]
    for k in arg_keys:
        v = params.get(k)
        if isinstance(v, (dict, list)):
            v = json.dumps(v, sort_keys=True, default=str)
        bits.append((k, v))
    return tuple(bits)


def _multiset(calls: Iterable[Call], arg_keys: Optional[list[str]]) -> dict:
    out: dict[tuple, int] = {}
    for call in calls:
        k = _key_for(call, arg_keys)
        out[k] = out.get(k, 0) + 1
    return out


# --------------------------------------------------------------------------- #
# Match modes
# --------------------------------------------------------------------------- #
def match_strict(actual: list[Call], expected: list[Call],
                 arg_keys: Optional[list[str]] = None) -> MatchResult:
    """Same names, same order, same args (subject to arg_keys)."""
    order_violations = []
    n = max(len(actual), len(expected))
    for i in range(n):
        a = actual[i] if i < len(actual) else None
        e = expected[i] if i < len(expected) else None
        if a is None or e is None or _key_for(a, arg_keys) != _key_for(e, arg_keys):
            order_violations.append((
                i,
                f"{e[0]}{e[1] if e else ''}" if e else "<missing>",
                f"{a[0]}{a[1] if a else ''}" if a else "<missing>",
            ))
    matched = (len(order_violations) == 0)
    a_counts = _multiset(actual, arg_keys)
    e_counts = _multiset(expected, arg_keys)
    missing = _diff_multiset(e_counts, a_counts)
    extra = _diff_multiset(a_counts, e_counts)
    return MatchResult(
        matched=matched, mode="strict",
        actual_count=len(actual), expected_count=len(expected),
        missing=missing, extra=extra,
        order_violations=order_violations or None,
    )


def match_unordered(actual: list[Call], expected: list[Call],
                    arg_keys: Optional[list[str]] = None) -> MatchResult:
    """Same multiset of (name, args) regardless of order."""
    a = _multiset(actual, arg_keys)
    e = _multiset(expected, arg_keys)
    missing = _diff_multiset(e, a)
    extra = _diff_multiset(a, e)
    matched = (not missing and not extra)
    return MatchResult(
        matched=matched, mode="unordered",
        actual_count=len(actual), expected_count=len(expected),
        missing=missing, extra=extra,
    )


def match_subset(actual: list[Call], expected: list[Call],
                 arg_keys: Optional[list[str]] = None) -> MatchResult:
    """Actual is a sub-multiset of expected (no extras allowed)."""
    a = _multiset(actual, arg_keys)
    e = _multiset(expected, arg_keys)
    extra = _diff_multiset(a, e)
    missing = _diff_multiset(e, a)  # informational
    matched = not extra
    return MatchResult(
        matched=matched, mode="subset",
        actual_count=len(actual), expected_count=len(expected),
        missing=missing, extra=extra,
    )


def match_superset(actual: list[Call], expected: list[Call],
                   arg_keys: Optional[list[str]] = None) -> MatchResult:
    """Actual is a super-multiset of expected (no missing allowed)."""
    a = _multiset(actual, arg_keys)
    e = _multiset(expected, arg_keys)
    missing = _diff_multiset(e, a)
    extra = _diff_multiset(a, e)  # informational
    matched = not missing
    return MatchResult(
        matched=matched, mode="superset",
        actual_count=len(actual), expected_count=len(expected),
        missing=missing, extra=extra,
    )


def _diff_multiset(a: dict, b: dict) -> list[Call]:
    """Return calls present in `a` but not in `b` (multiset semantics)."""
    out: list[Call] = []
    for key, count in a.items():
        excess = count - b.get(key, 0)
        if excess > 0:
            name = key[0]
            params = {}
            for entry in key[1:]:
                if isinstance(entry, tuple) and len(entry) == 2:
                    k, v = entry
                    try:
                        v = json.loads(v) if isinstance(v, str) and v.startswith(("{", "[")) else v
                    except (TypeError, json.JSONDecodeError):
                        pass
                    params[k] = v
            out.extend([(name, params)] * excess)
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def match(mode: str, actual: list[Call], expected: list[Call],
          arg_keys: Optional[list[str]] = None) -> MatchResult:
    if mode not in MATCH_MODES:
        raise ValueError(f"mode must be one of {MATCH_MODES}, got {mode!r}")
    if mode == "strict":
        return match_strict(actual, expected, arg_keys)
    if mode == "unordered":
        return match_unordered(actual, expected, arg_keys)
    if mode == "subset":
        return match_subset(actual, expected, arg_keys)
    return match_superset(actual, expected, arg_keys)


def load_expected_jsonl(path: str) -> list[Call]:
    """Load an expected trajectory from JSONL. Each line is one call:
    `{"name": "Read", "input": {"path": "..."}}`."""
    out: list[Call] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ev = json.loads(line)
        out.append((ev["name"], ev.get("input") or ev.get("params") or {}))
    return out


# --------------------------------------------------------------------------- #
# CLI (debugging helper)
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 3:
        print("Usage: trajectory.py <mode> <expected.jsonl> <actual.jsonl> [arg_key,...]",
              file=sys.stderr)
        return 64
    mode = args[0]
    expected = load_expected_jsonl(args[1])
    actual = load_expected_jsonl(args[2])
    arg_keys = args[3].split(",") if len(args) > 3 else None
    result = match(mode, actual, expected, arg_keys)
    out = {
        "matched": result.matched,
        "mode": result.mode,
        "actual_count": result.actual_count,
        "expected_count": result.expected_count,
        "missing": [{"name": n, "input": p} for n, p in result.missing],
        "extra":   [{"name": n, "input": p} for n, p in result.extra],
        "order_violations": result.order_violations,
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result.matched else 1


if __name__ == "__main__":
    sys.exit(main())
