---
name: evaluate-agent-behavior
description: "Score an agent on what it actually did vs what its definition promised. Two modes: replay grading over an existing transcript, or fixture run that exercises the agent against test prompts. Use after a release, after an agent misbehaves, or as periodic team-quality coverage. v0.1 ships replay-only; fixture runner lands in v0.2."
disable-model-invocation: false
user-invocable: true
argument-hint: "<agent-file> <transcript-or-fixture>"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
model: sonnet
---

# /evaluate-agent-behavior — Phase 3 behavioral grader

The static linter (`/evaluate-agent`) scores an agent's *definition*. The judge (`--deep`) scores its *clarity*. This skill scores the **gap between what the agent said it would do and what it did**.

The instruction-following gap (agent claims a thing, env shows it didn't happen) is the single highest-signal behavioral failure mode — see [arXiv 2601.03269](https://arxiv.org/html/2601.03269) and [arXiv 2510.03999v3](https://arxiv.org/html/2510.03999v3).

## Quick start

```bash
# Mode A: replay an existing transcript (lib/eval/replay.py)
/evaluate-agent-behavior \
  .claude/agents/code-reviewer.md \
  ~/.claude/projects/<slug>/subagents/agent-2026-04-29-1142.jsonl

# Mode A: override the max-turns expected band
/evaluate-agent-behavior --max-turns 30 .claude/agents/api-engineer.md transcript.jsonl

# Mode B: fixture runner — exercise an agent against canned prompts
python3 plugins/agents-team/lib/eval/runner.py \
  --agent .claude/agents/api-engineer.md \
  --fixture-dir plugins/agents-team/templates/eval-fixtures/behavior-fixtures/domain-engineer \
  --canned

# Mode B: live (requires `claude` CLI on PATH; sandboxed env only)
python3 plugins/agents-team/lib/eval/runner.py \
  --agent .claude/agents/api-engineer.md \
  --fixture-dir plugins/agents-team/templates/eval-fixtures/behavior-fixtures/domain-engineer
```

## Mode B fixture layout

A fixture set lives under `templates/eval-fixtures/behavior-fixtures/<archetype>/`:

```text
<archetype>/
  prompts/<n>.md       input the runner sends to the agent
  expected/<n>.jsonl   reference tool-call trajectory (one event per line)
  canned/<n>.jsonl     pre-recorded transcript (used in --canned mode)
  assertions.yaml      per-fixture match_mode + outcome assertions
```

`assertions.yaml` shape:

```yaml
01-add-endpoint:
  match_mode: subset       # one of strict | unordered | subset | superset
  arg_keys: [path]         # optional; defaults to name-only matching
  expected_outcome:
    - kind: text_contains  # text_contains | text_not_contains
      value: "tests pass"
```

3 archetype sets ship with the plugin (orchestrator, domain-engineer, qa-engineer; 6 fixtures total). Adding a new set is the natural extension path.

## Rules (v0.2)

`lib/eval/replay.py` reads a Claude Code subagent transcript (JSONL) and grades:

| Rule ID | Severity | What it catches |
|---------|----------|-----------------|
| `behavioral.tool_whitelist_violation` | critical | Tool calls not declared in the agent's `tools` field |
| `behavioral.no_declared_tools`        | suggestion | Agent has no `tools:` so whitelist cannot be measured |
| `behavioral.step_efficiency_exceeded` | warning | Turn count exceeds the expected band |
| `behavioral.domain_adherence_violation` | warning | Tool calls touch paths outside the agent's `owned_paths` |
| `behavioral.self_correction_failure`    | warning | Same tool call repeated 3+ times consecutively |
| `behavioral.error_silently_swallowed`   | warning | Tool returned an error and the agent's next text didn't surface it |
| `behavioral.output_format_drift`        | suggestion | Body promised "## Critical / Warnings / …" sections that the response is missing |
| `behavioral.instruction_following_gap_claim_detected` | suggestion | Agent made verifiable claims ("I have updated X", "Tests now pass"); env-verification is v0.3 |

Output conforms to `lib/eval/schema/v1.json` with `produced_by: "behavioral"` and a `behavioral_metadata` block listing `transcript_path`, `turn_count`, `tool_call_count`, and `text_block_count`.

## v0.3 scope (deferred — see issue #18 for the fixture runner)

- **Domain adherence (real LLM-judge)** — current v0.2 implementation is a deterministic path-prefix heuristic; v0.3 will add an LLM-judge that understands "this file is implied by the description" beyond literal path matching.
- **Instruction-following gap (real env-verification)** — v0.2 detects claims ("I have updated X", "Tests now pass") and emits a suggestion. v0.3 will run filesystem / `git status` / last-test-exit-code verification to upgrade matched claims to a `critical` finding when the env contradicts them.
- **Fixture runner** — per-archetype prompts in `templates/eval-fixtures/<archetype>/`, headless `claude --agent` runner, LangChain-style trajectory match (strict / unordered / subset / superset). Tracked in #18.

## Where transcripts live

Claude Code stores subagent transcripts at:

```
~/.claude/projects/<project-slug>/subagents/agent-*.jsonl
```

Each event is one JSON object per line. `replay.py` is robust to malformed lines and to the few transcript shapes Claude Code uses.

## Anti-goals

- **Do not** run behavioral evals against production credentials. Fixtures only.
- **Do not** grade the agent's *output content* (code quality, copy quality). That's a different evaluator.
- **Do not** infer intent from a single failing run. Behavioral findings need ≥3 occurrences before they ride into a verdict change.

## Sources

- LangChain `agentevals` — https://github.com/langchain-ai/agentevals (trajectory match modes)
- Braintrust agent eval framework — https://www.braintrust.dev/articles/ai-agent-evaluation-framework (tool selection accuracy, parameter correctness, step efficiency)
- Anthropic *Demystifying evals for AI agents* — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Instruction-Following Gap — https://arxiv.org/html/2601.03269 + https://arxiv.org/html/2510.03999v3
- METR / AISI Inspect — https://evaluations.metr.org/elicitation-protocol/ (failure taxonomy: spurious vs real)
