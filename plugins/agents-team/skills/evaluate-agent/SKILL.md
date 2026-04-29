---
name: evaluate-agent
description: "Statically lint a Claude Code agent or skill file against a citation-backed rule set (frontmatter, description, tool hygiene, model fit, body structure, anti-patterns). Use proactively before merging any change to .claude/agents/ or any SKILL.md. Use when an agent is misbehaving or the team adds a new specialist."
disable-model-invocation: false
user-invocable: true
argument-hint: "<path-to-agent-or-skill>"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
model: haiku
---

# /evaluate-agent — Static linter for agents and skills

Phase 1 of the agents-team evaluator. Deterministic. Cheap. CI-safe. Every rule cites a source.

## Quick start

```bash
# Lint one file; writes JSON + Markdown to .claude/agent-quality/<name>.{json,md}
/evaluate-agent .claude/agents/code-reviewer.md

# Print Markdown report to stdout (don't write files)
/evaluate-agent --stdout .claude/agents/code-reviewer.md

# CI mode: exit nonzero on `revise` or `reject` verdicts
/evaluate-agent --ci .claude/agents/code-reviewer.md

# Strict mode: promote suggestion-severity findings to warnings
/evaluate-agent --strict path/to/SKILL.md
```

## What it checks

Six dimensions, with role-aware weights (agents weight description higher than `tool_hygiene`; skills the opposite):

| Dimension       | Sample rules                                                                                          |
|-----------------|-------------------------------------------------------------------------------------------------------|
| `frontmatter`   | `name` valid + present, `description` present, `name` not reserved, model not retired                |
| `description`   | length 80–400 (agents), no first/second person, has "use when"/"use proactively" trigger             |
| `tool_hygiene`  | `tools` set explicitly (not inherited), no write tools on reviewer roles, Bash safeguards            |
| `model_fit`     | Opus on read-only roles → warn; Haiku on architecture/orchestrator roles → warn                       |
| `body_structure`| Agents: "When invoked" + "Constraints" sections. Skills: body <500 lines, TOC if >100 lines           |
| `anti_patterns` | Prompt-injection smell, hardcoded absolute paths, body/tool contradictions                            |

Every rule has a stable ID (e.g. `tool_hygiene.write_on_review_role`) and a citation (Anthropic spec or published prior art).

## Output

- **JSON**: conforms to `lib/eval/schema/v1.json`. Fields: `agent`, `path`, `kind`, `overall.{score,grade,verdict}`, `dimensions.{frontmatter,description,…}.{score,weight,findings}`, `findings[]`, `produced_by`, `produced_at`, `schema_version`.
- **Markdown**: rendered via `lib/eval/render.sh`. Verdict line, dimension table, findings grouped by severity (critical / warning / suggestion).
- **Default paths**: `.claude/agent-quality/<agent>.json` + sibling `.md`. The skill writes these unless `--stdout` is passed.

## Exit codes

| Code | Verdict   | Meaning                                                |
|------|-----------|--------------------------------------------------------|
| `0`  | `ship`    | No critical findings; score ≥ 75                       |
| `1`  | `revise`  | No critical findings; score 50–74                      |
| `2`  | `reject`  | At least one critical finding, OR score < 50           |
| `64` | —         | Bad CLI args                                           |
| `66` | —         | Target file not found                                  |

`--ci` carries verdict-based exit codes through; without it, the skill exits 0 (so a one-shot `/evaluate-agent` doesn't kill an interactive session).

## When to use this skill

- **Before merging** any change to `.claude/agents/` or any `SKILL.md`.
- **In CI** on every PR that touches `.claude/`.
- **When the orchestrator under-delegates** to a specialist — usually a description-clarity issue.
- **As a sweep** — run across an entire team's roster to spot weak links.

## Anti-patterns

- Treating the linter's score as authoritative without reading the evidence.
- Ignoring `warning`-severity findings — they are leading indicators of misbehavior.
- Auto-applying suggested fixes without reviewing the diff.
- Adding rules that aren't backed by Anthropic spec or published prior art (those go in `experimental/` only).

## Implementation

- `lib/eval/lint.py` — Python 3, stdlib only. Parses frontmatter without pyyaml.
- `lib/eval/render.sh` — jq-based Markdown renderer.
- `lib/eval/lint.sh` — entry point combining both.
- `lib/eval/schema/v1.json` — JSON Schema for the report shape.

## References

- Anthropic Sub-agents — https://code.claude.com/docs/en/sub-agents
- Anthropic Skill best practices — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic *Demystifying evals for AI agents* — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
