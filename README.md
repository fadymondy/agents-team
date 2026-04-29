# agents-team

A Claude Code plugin that turns "build me an agent team" from a one-off craft into a repeatable, measurable pipeline.

Three pillars:

- **`/team-gen`** — give it a product description, get a complete `.claude/` directory: orchestrator + specialists + skills + rules + hooks, all standards-compliant. ([docs](docs/team-gen.md))
- **`/meet`** — streamed multi-agent meeting on a topic with structured minutes. ([docs](docs/meet.md))
- **`/evaluate-agent`** — score any agent (or skill) against a citation-backed rubric. Static linter ships now; LLM-as-judge and behavioral harness layer on top. ([docs](docs/evaluator.md))

## Install

```bash
git clone https://github.com/fadymondy/agents-team.git
claude plugin install ./agents-team/plugins/agents-team
```

## Quick start

```bash
# Generate a team from a PRD
/team-gen ./my-product-spec.md --target .

# Hold a meeting on a topic
/meet "Should we ship the v2 migration this quarter?"

# Lint an agent
/evaluate-agent .claude/agents/code-reviewer.md
```

## What you get end-to-end

```text
$ /team-gen ./docs/product.md --target .
...
Generated team for E-Shop at /Users/me/my-shop/.claude
  agents: 6
  rules: 8
  hooks: 4
  settings: 1

=== Self-evaluation ===
  shop-orch.md           A  100/100  ship
  api-engineer.md        A   97/100  ship
  web-engineer.md        A  100/100  ship
  payments-engineer.md   A   95/100  ship
  qa-engineer.md         A   97/100  ship
  security-engineer.md   A  100/100  ship
=== Self-eval worst verdict: exit 0 ===
```

Every produced agent is linted before the run exits. A `reject` verdict on any file fails the run.

## Why

The author runs three large agent teams (sentra-hub ~14 agents, orch ~42 agents, the Orchestra team ~40 agents) and was hand-rolling each from scratch. This plugin extracts the patterns that worked, lets you compose new teams from them, and tells you when an agent is below standard before it makes a mess.

## Architecture in one paragraph

The evaluator is the architectural anchor. Every rule cites Anthropic's spec or published prior art (LangChain `agentevals`, Braintrust, Galileo 2026, Anthropic's *Demystifying evals*). The static linter (Phase 1) catches deterministic issues. The LLM-as-judge (Phase 2) catches nuance with one isolated call per dimension. The behavioral harness (Phase 3) catches the gap between what an agent says it did and what the environment shows. The generator runs the static linter on every produced file before exiting, so a generated team starts at grade A by construction.

See [`docs/evaluator.md`](docs/evaluator.md) for the rubric, the schema, and the CI integration recipe.

## Status

v0.1 in development. See the [v0.1 milestone](https://github.com/fadymondy/agents-team/milestone/1) for the breakdown.

## Contributing

See [`docs/contributing.md`](docs/contributing.md) — adding archetypes, adding rubric line-items, the gh-pms workflow.

## License

[MIT](LICENSE)
