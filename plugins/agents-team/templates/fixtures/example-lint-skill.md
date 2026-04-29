---
name: shop-lint
description: "Run e-shop's full lint stack across changed files: ESLint for TypeScript, Prettier for formatting, knip for dead exports, and the agents-team agent linter for any .claude/ change. Use proactively before opening a PR."
disable-model-invocation: false
user-invocable: true
argument-hint: "[--changed | --all]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
model: haiku
---

# /shop-lint — Full lint sweep for the e-shop

## Quick start

```bash
/shop-lint --changed
/shop-lint --all
```

## What it checks

| Rule ID | Severity | What it catches |
|---------|----------|-----------------|
| `eslint.error` | critical | TypeScript / JS errors in `services/api/`, `apps/web/` |
| `prettier.format` | warning | Files outside the project's formatting baseline |
| `knip.unused-exports` | suggestion | Dead exports nothing imports |
| `agent-quality.evaluate` | warning | Any `.claude/agents/*.md` or `**/SKILL.md` whose evaluator verdict is `revise` or `reject` |

## Output

A summary table grouped by file, then by rule. Returns nonzero exit code on any `error` finding so it can gate CI.

## Exit codes

- `0` — clean run, ready to push
- `1` — warnings only (non-blocking with `--changed`)
- `2` — errors (always blocking)

## When to use this skill

- Before opening a PR (the most common path).
- In CI as a pre-merge gate.
- After upgrading a dependency to catch lint config breakage.

## Anti-patterns

- Running `--all` before every commit — it scans the entire repo. Use `--changed` for the inner loop.
- Suppressing rules globally to make a file pass — fix the file or document the suppression in code with a TODO.
- Auto-applying suggested fixes without a diff review.

## References

- ESLint config: `eslint.config.mjs`
- Prettier config: `.prettierrc`
- Knip config: `knip.json`
- Agent linter: `plugins/agents-team/lib/eval/lint.py`
