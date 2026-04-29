#!/usr/bin/env python3
"""
render.py — fill `{{placeholder}}` tokens in template files.

Used by /team-gen to materialize agent / skill / rule / hook templates into
a generated team's .claude/ directory.

Usage:
    render.py <template-file> <values.json>           # → prints to stdout
    render.py <template-file> <values.json> -o <out>  # → writes to <out>

Replacement rules:
    {{key}}           — replace with values[key]; unknown keys raise unless --tolerant
    {{key|default}}   — replace with values[key]; fall back to literal `default`
    {{LIST_OF list}}  — render the list as a YAML-flow list `[a, b, c]`

Lists in values can also be referenced as {{key}} — they render comma-joined.
Zero deps; stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


_TOKEN = re.compile(r"\{\{\s*([A-Z_]+\s+)?([A-Za-z0-9_-]+)(?:\s*\|\s*([^}]+?))?\s*\}\}")


def render(template: str, values: dict, tolerant: bool = False) -> str:
    def sub(m: re.Match) -> str:
        directive = (m.group(1) or "").strip().upper()
        key = m.group(2)
        default = m.group(3)
        if key not in values:
            if default is not None:
                return default
            if tolerant:
                return m.group(0)
            raise KeyError(f"render.py: missing value for `{key}`")
        v = values[key]
        if directive == "LIST_OF":
            if not isinstance(v, list):
                raise TypeError(f"`{key}` is not a list (got {type(v).__name__})")
            return "[" + ", ".join(json.dumps(x) for x in v) + "]"
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    return _TOKEN.sub(sub, template)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("template", help="Path to a .template (or any file with {{tokens}})")
    p.add_argument("values", help="Path to JSON file with replacement values")
    p.add_argument("-o", "--output", help="Output path; default: stdout")
    p.add_argument("--tolerant", action="store_true",
                   help="Leave unknown tokens as-is instead of erroring")
    args = p.parse_args(argv)

    if not os.path.isfile(args.template):
        print(f"render.py: not a file: {args.template}", file=sys.stderr)
        return 66
    if not os.path.isfile(args.values):
        print(f"render.py: not a file: {args.values}", file=sys.stderr)
        return 66

    template = Path(args.template).read_text(encoding="utf-8")
    values = json.loads(Path(args.values).read_text(encoding="utf-8"))

    try:
        out = render(template, values, tolerant=args.tolerant)
    except KeyError as e:
        print(f"render.py: {e}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
