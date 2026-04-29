# Eval fixtures

Inputs the evaluator's behavioral mode (`/evaluate-agent-behavior`) consumes. Two kinds:

```
known-good/        # well-formed fixtures the static linter must pass cleanly
known-bad/         # broken fixtures the static linter must reject
behavior-fixtures/ # (v0.2) per-archetype prompts + reference transcripts
calibration/       # (v0.2) hand-graded files for judge calibration (Spearman ≥ 0.80)
```

## known-good / known-bad

Used by the linter's regression tests. Every rule should have at least one fixture that exercises it.

## behavior-fixtures (v0.2)

When the fixture runner lands in v0.2, this directory will hold one subdirectory per archetype (`orchestrator/`, `domain-engineer/`, `qa/`, etc.). Each archetype directory contains:

- `prompts/*.md` — input prompts the runner sends to a fresh `claude --agent <name>` invocation.
- `expected/*.jsonl` — the reference trajectory we expect the agent to produce. Used by LangChain-style trajectory matchers (strict / unordered / subset / superset).
- `assertions.yaml` — final-state assertions (file diff, exit code, output regex).

## calibration (v0.2)

Hand-graded fixtures used to measure how closely the LLM-as-judge matches a human rater. Target: ≥0.80 Spearman correlation per Galileo 2026 guidance. Each entry is `<agent>.md` + `<agent>.expected.json` (the human grade).

Re-run `lib/eval/calibrate.sh` after any rubric change. A drop below 0.75 blocks the rubric change.
