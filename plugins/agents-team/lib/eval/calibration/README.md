# Calibration set

15 fixture pairs the LLM-as-judge is measured against. Each pair is `<name>.md` (the agent / skill file) plus `<name>.expected.json` (the human grade).

The `calibrate.sh` script in the parent directory iterates these pairs, runs the judge, and reports a per-dimension Spearman correlation against the human grades. The Galileo-2026 target is ≥0.80; the CI floor is 0.75 — anything lower blocks rubric / judge changes.

## Score range

The set is built to span the full A–F band so the Spearman calculation has variance to work with:

| Prefix | Grade target | Count | Source                                          |
|--------|-------------:|------:|-------------------------------------------------|
| `a-`   | A            | 4     | The existing `templates/fixtures/example-*.md`  |
| `b-`   | B            | 3     | Synthetic — well-formed minus one section       |
| `c-`   | C            | 3     | Synthetic — vague description / role mismatch   |
| `d-`   | D            | 3     | The existing `templates/eval-fixtures/known-bad/`|
| `f-`   | F            | 2     | Synthetic — multi-fault disasters                |

## Generation

`_generate.py` builds the set programmatically. The expected.json files are derived from the **static linter** as the v0.1 baseline. This is intentionally tautological — when calibrate.sh runs in `--static` mode it scores Spearman 1.0 across every dimension, which proves the pipeline works.

The real calibration begins when:

1. The expected.json files are **hand-tuned** to reflect a real human rater's judgment (catching things the static linter misses — description clarity, internal contradictions, role/tool mismatch nuance).
2. `calibrate.sh` runs without `--static`, exercising the LLM-as-judge against the hand-graded set, with `ANTHROPIC_API_KEY` set.

## Running

```bash
# Static-mode (no API needed; v0.1 baseline)
bash plugins/agents-team/lib/eval/calibrate.sh --static

# Real judge run (requires ANTHROPIC_API_KEY + `pip install anthropic`)
ANTHROPIC_API_KEY=sk-ant-... bash plugins/agents-team/lib/eval/calibrate.sh

# Custom CI threshold
bash plugins/agents-team/lib/eval/calibrate.sh --threshold 0.7
```

Exit codes:

| Code | Meaning                                                 |
|-----:|---------------------------------------------------------|
| `0`  | All dimensions ≥ threshold                              |
| `1`  | At least one dimension below threshold                  |
| `64` | Bad CLI args                                            |
| `65` | Live judge requested but `ANTHROPIC_API_KEY` not set    |
| `66` | Calibration directory missing or empty                  |

## Adding a fixture

1. Drop `<name>.md` into this directory (or extend `_generate.py`).
2. Drop `<name>.expected.json` next to it. Schema must match `lib/eval/schema/v1.json`. Hand-grade the per-dimension scores to reflect what you, as a human reviewer, would say — not what the static linter says.
3. Re-run calibrate.sh to confirm Spearman did not regress.

## Anti-goals

- **Do not use the static linter to bootstrap expected scores in production.** It's a v0.1 starting baseline only; replace each expected.json with a real human grade as the set matures.
- **Do not expand the set with synthetic-only fixtures.** Real agents (de-personalized) from sentra-hub / orch are higher-signal.
- **Do not lower the threshold to make calibrate.sh pass.** A failing dimension means the judge is mis-scoring; investigate the rubric or the judge prompt, not the threshold.
