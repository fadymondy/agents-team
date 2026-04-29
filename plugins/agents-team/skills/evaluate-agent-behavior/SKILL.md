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
# Replay a transcript that already exists
/evaluate-agent-behavior \
  .claude/agents/code-reviewer.md \
  ~/.claude/projects/<slug>/subagents/agent-2026-04-29-1142.jsonl

# Override the max-turns expected band
/evaluate-agent-behavior --max-turns 30 .claude/agents/api-engineer.md transcript.jsonl
```

## v0.1 scope (replay only)

`lib/eval/replay.py` reads a Claude Code subagent transcript (JSONL) and grades:

| Rule ID | Severity | What it catches |
|---------|----------|-----------------|
| `behavioral.tool_whitelist_violation` | critical | Tool calls not declared in the agent's `tools` field |
| `behavioral.no_declared_tools`        | suggestion | Agent has no `tools:` so whitelist cannot be measured |
| `behavioral.step_efficiency_exceeded` | warning | Turn count exceeds the expected band |

Output conforms to `lib/eval/schema/v1.json` with `produced_by: "behavioral"` and a `behavioral_metadata` block listing `transcript_path`, `turn_count`, and `tool_call_count`.

## v0.2 scope (deferred — see issue #12 for the full plan)

- **Domain adherence** (LLM-judge): tool calls touch only files / services named or implied by the description.
- **Self-correction signal**: after a wrong tool call, is the next call corrective?
- **Output-format adherence**: does the response have the sections the body promised?
- **Error surfacing vs silent failure**: when a tool returns an error, does the agent report or pretend success?
- **Instruction-following gap detector**: parse agent claims ("I have updated X"), verify against env state.
- **Fixture runner**: per-archetype prompts in `templates/eval-fixtures/<archetype>/`, headless `claude --agent` runner, LangChain-style trajectory match (strict / unordered / subset / superset).

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
