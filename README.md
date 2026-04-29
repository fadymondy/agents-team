# agents-team

A Claude Code plugin that turns "build me an agent team" from a one-off craft into a repeatable, measurable pipeline.

Three pillars:

- **`/team-gen`** — give it a product description, get a complete `.claude/` directory: orchestrator + specialists + skills + rules + hooks, all standards-compliant.
- **`/meet`** — streamed multi-agent meeting on a topic with structured minutes.
- **`/evaluate-agent`** — score any agent (or skill) against a citation-backed rubric. Static linter ships first; LLM-as-judge and behavioral harness layer on top.

## Install

```bash
git clone https://github.com/fadymondy/agents-team.git
claude plugin install ./agents-team/plugins/agents-team
```

## Quick start

```bash
# Generate a team from a PRD
/team-gen ./my-product-spec.md

# Hold a meeting on a topic
/meet "Should we ship the v2 migration this quarter?"

# Lint an agent
/evaluate-agent .claude/agents/code-reviewer.md
```

## Why

The author runs three large agent teams (sentra-hub ~14 agents, orch ~42 agents, the Orchestra team ~40 agents) and was hand-rolling each from scratch. This plugin extracts the patterns that worked, lets you compose new teams from them, and tells you when an agent is below standard before it makes a mess.

## Status

v0.1 in development. See [issues](https://github.com/fadymondy/agents-team/issues) for the breakdown.

## License

MIT
