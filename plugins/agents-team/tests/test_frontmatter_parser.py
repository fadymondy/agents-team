"""Aggregate tests for the YAML-frontmatter parser in lib/eval/lint.py."""
from __future__ import annotations

import lint as lint_mod  # type: ignore


def parse(content: str):
    # Strip the file boundary; parse just the frontmatter chunk.
    lines = content.splitlines()
    if lines and lines[0] == "---":
        end = lines.index("---", 1)
        return lint_mod.parse_frontmatter(lines[1:end], offset=2)
    return ({}, {})


def test_inline_list():
    fm, _ = parse("---\ntools: [Read, Edit, Bash]\n---\n")
    assert fm["tools"] == ["Read", "Edit", "Bash"]


def test_block_list_of_scalars():
    fm, _ = parse("---\ntools:\n  - Read\n  - Edit\n  - Bash\n---\n")
    assert fm["tools"] == ["Read", "Edit", "Bash"]


def test_quoted_string_strips_quotes():
    fm, _ = parse("---\ndescription: \"Reviews code for security.\"\n---\n")
    assert fm["description"] == "Reviews code for security."


def test_unquoted_string():
    fm, _ = parse("---\nname: api-engineer\n---\n")
    assert fm["name"] == "api-engineer"


def test_boolean_values():
    fm, _ = parse("---\nbackground: true\nfoo: false\n---\n")
    assert fm["background"] is True
    assert fm["foo"] is False


def test_integer_values():
    fm, _ = parse("---\nmaxTurns: 50\n---\n")
    assert fm["maxTurns"] == 50


def test_comments_skipped():
    fm, _ = parse("---\n# this is a comment\nname: x\n---\n")
    assert fm == {"name": "x"}


def test_blank_lines_ignored():
    fm, _ = parse("---\n\nname: x\n\nmodel: opus\n\n---\n")
    assert fm == {"name": "x", "model": "opus"}


def test_line_numbers_recorded():
    fm, lines = parse("---\nname: x\nmodel: opus\n---\n")
    # offset=2 means name at file line 2, model at file line 3.
    assert lines["name"] == 2
    assert lines["model"] == 3


def test_empty_frontmatter_returns_empty_dict():
    fm, _ = lint_mod.parse_frontmatter([], offset=2)
    assert fm == {}
