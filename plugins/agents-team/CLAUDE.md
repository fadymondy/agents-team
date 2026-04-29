# agents-team plugin

Three pillars:

1. **Generator** — `/team-gen` reads a product description and produces a full `.claude/` agent team (orchestrator + specialists + skills + rules + hooks).
2. **Meeting** — `/meet` runs a streamed multi-agent meeting on a topic and writes structured minutes.
3. **Evaluator** — `/evaluate-agent` (and `/evaluate-agent-behavior`) scores any agent definition or transcript against a citation-backed rubric.

## Layout

```
plugins/agents-team/
  .claude-plugin/plugin.json   # plugin manifest
  agents/                      # plugin's own subagents (not generated)
  skills/                      # /team-gen, /meet, /evaluate-agent, /evaluate-agent-behavior
  rules/                       # plugin-internal rules (rare)
  hooks/                       # plugin-internal hooks (rare)
  templates/                   # archetypes and fixtures the generator emits
    agents/                    # 8+ agent archetypes
    skills/                    # skill archetypes
    rules/                     # numbered rule templates
    hooks/                     # notify / idle-gate / session-init scripts
    eval-fixtures/             # behavioral test fixtures per archetype
  lib/                         # shell + helper scripts
    eval/
      schema/v1.json           # evaluator output schema
      rubric.md                # judge rubric (sourced)
      render.sh                # JSON → Markdown renderer
      lint.sh                  # static linter entry point
```

## Conventions

- Every rubric line-item in the evaluator cites a source (Anthropic spec or published prior art). Unsourced rules go in `experimental/` and are off by default.
- Skill front matter follows the orch superset: `name, description, model, color, memory, maxTurns, tools, background?, effort?, isolation?`.
- Generated team output goes to the user's working directory under `.claude/`, never inside the plugin.
- Reports default to `.claude/agent-quality/<agent>.json` + sibling `.md`.
