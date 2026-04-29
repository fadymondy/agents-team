"""Tests for lib/eval/trajectory.py — the four match modes."""
from __future__ import annotations

import pytest

import trajectory as traj  # type: ignore


# Shared helpers
def call(name, **input):
    return (name, input)


# ---------------------------------------------------------------------------
# strict
# ---------------------------------------------------------------------------
class TestStrict:
    def test_identical_sequence_matches(self):
        seq = [call("Read", path="a"), call("Edit", path="a")]
        r = traj.match("strict", seq, seq, arg_keys=["path"])
        assert r.matched is True
        assert r.order_violations is None

    def test_different_order_fails(self):
        a = [call("Read", path="a"), call("Edit", path="a")]
        e = [call("Edit", path="a"), call("Read", path="a")]
        r = traj.match("strict", a, e, arg_keys=["path"])
        assert r.matched is False
        assert r.order_violations  # non-empty

    def test_different_args_fails(self):
        a = [call("Read", path="x")]
        e = [call("Read", path="y")]
        r = traj.match("strict", a, e, arg_keys=["path"])
        assert r.matched is False

    def test_args_ignored_when_arg_keys_none(self):
        a = [call("Read", path="x")]
        e = [call("Read", path="y")]
        r = traj.match("strict", a, e, arg_keys=None)
        assert r.matched is True


# ---------------------------------------------------------------------------
# unordered
# ---------------------------------------------------------------------------
class TestUnordered:
    def test_same_calls_different_order_matches(self):
        a = [call("Read", path="a"), call("Edit", path="a")]
        e = [call("Edit", path="a"), call("Read", path="a")]
        r = traj.match("unordered", a, e, arg_keys=["path"])
        assert r.matched is True

    def test_extra_call_fails(self):
        a = [call("Read", path="a"), call("Edit", path="a"), call("Bash", command="ls")]
        e = [call("Read", path="a"), call("Edit", path="a")]
        r = traj.match("unordered", a, e, arg_keys=["path"])
        assert r.matched is False
        assert any(x[0] == "Bash" for x in r.extra)

    def test_missing_call_fails(self):
        a = [call("Read", path="a")]
        e = [call("Read", path="a"), call("Edit", path="a")]
        r = traj.match("unordered", a, e, arg_keys=["path"])
        assert r.matched is False
        assert any(x[0] == "Edit" for x in r.missing)


# ---------------------------------------------------------------------------
# subset
# ---------------------------------------------------------------------------
class TestSubset:
    def test_actual_is_subset_matches(self):
        a = [call("Read", path="a")]
        e = [call("Read", path="a"), call("Edit", path="a")]
        r = traj.match("subset", a, e, arg_keys=["path"])
        assert r.matched is True

    def test_actual_has_extra_fails(self):
        a = [call("Read", path="a"), call("Bash", command="ls")]
        e = [call("Read", path="a")]
        r = traj.match("subset", a, e, arg_keys=["path"])
        assert r.matched is False


# ---------------------------------------------------------------------------
# superset
# ---------------------------------------------------------------------------
class TestSuperset:
    def test_actual_covers_expected_matches(self):
        a = [call("Read", path="a"), call("Edit", path="a"), call("Bash", command="ls")]
        e = [call("Read", path="a"), call("Edit", path="a")]
        r = traj.match("superset", a, e, arg_keys=["path"])
        assert r.matched is True

    def test_actual_missing_expected_fails(self):
        a = [call("Read", path="a")]
        e = [call("Read", path="a"), call("Edit", path="a")]
        r = traj.match("superset", a, e, arg_keys=["path"])
        assert r.matched is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        traj.match("fuzzy", [], [], arg_keys=None)


def test_empty_actual_and_empty_expected_match_everywhere():
    for mode in ("strict", "unordered", "subset", "superset"):
        r = traj.match(mode, [], [], arg_keys=None)
        assert r.matched is True


def test_load_expected_jsonl_round_trip(tmp_path):
    p = tmp_path / "expected.jsonl"
    p.write_text(
        '{"name": "Read", "input": {"path": "a.ts"}}\n'
        '{"name": "Edit", "input": {"path": "a.ts"}}\n',
        encoding="utf-8",
    )
    seq = traj.load_expected_jsonl(str(p))
    assert seq == [("Read", {"path": "a.ts"}), ("Edit", {"path": "a.ts"})]
