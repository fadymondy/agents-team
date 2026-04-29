# Tests

The pytest suite for `agents-team`. Run from the repo root:

```bash
pip install pytest
pytest plugins/agents-team/tests/
```

## Layout

| File | What it covers |
|------|----------------|
| `conftest.py` | Wires `lib/eval/` and `lib/gen/` onto `sys.path`; provides `lint`, `write_md`, `rule_ids` fixtures |
| `test_frontmatter_parser.py` | Parser edge cases — inline lists, block lists, comments, blanks, line numbers, quoted strings |
| `test_lint_rules.py` | One test per static-linter rule ID. Inline fixtures (more readable than file-jumping). Each rule has at least one bad case + a baseline showing the canonical "good" fixture is unaffected. |
| `test_v01_regressions.py` | The three v0.1 bugs caught reactively — locked in so they cannot recur (orchestrator-with-"report", monitor-with-"cannot delegate", "Use before/after" trigger). Marked `regression`. |
| `test_render.py` | Snapshot-style checks on `render.sh` — verdict line, dimension table, severity grouping, source URL, summary one-liner, stdin-via-dash. Skipped when `jq` isn't installed. |
| `test_scaffold_gate.py` | The hardened `--no-self-eval` env-gate and `--min-grade` flag from #22. Forks real subprocesses; marked `slow`. |

## Running subsets

```bash
# Skip the subprocess-heavy scaffold tests (fast inner loop):
pytest plugins/agents-team/tests/ -m "not slow"

# Just the regression cases (post-bisect quick check):
pytest plugins/agents-team/tests/ -m regression
```

## Coverage status

| Dimension | Rules implemented in lint.py | Tested in test_lint_rules.py |
|-----------|----:|----:|
| frontmatter      | 7  | 7  |
| description      | 4  | 4  |
| tool_hygiene     | 4  | 3 (bash_without_safeguard_on_readonly is the only gap) |
| model_fit        | 2  | 2  |
| body_structure   | 4  | 3 (skill_no_toc_when_long is the only gap) |
| anti_patterns    | 5  | 5  |
| **Total**        | **26** | **24** |

The two gaps are tracked in #14 follow-up work — both rules are deterministic and testable; just not yet covered.

## Adding a new test

When you add a new linter rule in `lib/eval/lint.py`:

1. Add an inline-fixture test in `test_lint_rules.py` under the matching dimension section.
2. Mutate `GOOD_AGENT` (or `GOOD_SKILL`) to trip the new rule, assert the rule ID appears in `rule_ids(report)`.
3. Add a non-trivial baseline test if the rule has known-quirky negation cases (cf. `test_v01_regressions.py`).

When you add a new known-bad fixture under `templates/eval-fixtures/known-bad/by-rule/<rule_id>.md`, no test code change is needed — those fixtures are sweep-tested by CI (#15) using a shell loop, not by pytest.
