# Evaluator — score an agent against a citation-backed rubric

The evaluator is the architectural anchor of the plugin. It scores any agent or skill file across six dimensions, every rule cites a source (Anthropic spec or published prior art), and it produces the same v1-schema JSON whether run in static, judge, or behavioral mode.

Three phases:

| Phase | Skill | What it scores | When |
|-------|-------|----------------|------|
| 1. Static linter | [`/evaluate-agent`](../plugins/agents-team/skills/evaluate-agent/SKILL.md) | Definition (frontmatter, description, tools, model fit, body, anti-patterns) | Always. Free. CI-safe. |
| 2. LLM-as-judge  | `/evaluate-agent --deep` (same skill) | Description clarity, contradictions, role/tool mismatch nuance | When you want a human-grade read; costs tokens. |
| 3. Behavioral    | [`/evaluate-agent-behavior`](../plugins/agents-team/skills/evaluate-agent-behavior/SKILL.md) | Tool-whitelist adherence + step efficiency from a transcript (v0.1); domain adherence + instruction-following gap (v0.2) | After a release; periodic team-quality coverage. |

## Quick start

```bash
# Lint one agent, write JSON + Markdown to .claude/agent-quality/
/evaluate-agent .claude/agents/code-reviewer.md

# Print the Markdown report to stdout
/evaluate-agent --stdout .claude/agents/code-reviewer.md

# CI mode: nonzero exit on revise/reject
/evaluate-agent --ci .claude/agents/code-reviewer.md

# Strict: promote suggestions to warnings
/evaluate-agent --strict path/to/SKILL.md

# Phase 2 judge (costs tokens; needs ANTHROPIC_API_KEY)
/evaluate-agent --deep .claude/agents/code-reviewer.md

# Phase 3 replay (skeleton — v0.2 adds fixture runner)
/evaluate-agent-behavior \
  .claude/agents/code-reviewer.md \
  ~/.claude/projects/<slug>/subagents/agent-2026-04-29-1142.jsonl
```

## Output shape

JSON conforming to [`plugins/agents-team/lib/eval/schema/v1.json`](../plugins/agents-team/lib/eval/schema/v1.json):

```json
{
  "agent": "code-reviewer",
  "path": ".claude/agents/code-reviewer.md",
  "kind": "agent",
  "overall": { "score": 78, "grade": "B", "verdict": "ship" },
  "dimensions": {
    "frontmatter":     { "score": 95, "weight": 0.15, "findings": [] },
    "description":     { "score": 80, "weight": 0.25, "findings": [...] },
    "tool_hygiene":    { "score": 60, "weight": 0.15, "findings": [...] },
    "model_fit":       { "score": 100, "weight": 0.10, "findings": [] },
    "body_structure":  { "score": 75, "weight": 0.20, "findings": [...] },
    "anti_patterns":   { "score": 90, "weight": 0.15, "findings": [] }
  },
  "findings": [...],
  "produced_by": "static",
  "produced_at": "2026-04-29T11:30:00Z",
  "schema_version": "1.0.0"
}
```

Markdown render:

```
✅ Verdict: ship — Grade B (78/100)

## Critical findings (1)

- `tools.write_on_review_role` — Description says "reviews" but tools include Edit
  - Evidence: tools: [Read, Edit, Bash]
  - Fix: Remove Edit; reviewer agents should be read-only.
  - Source: https://code.claude.com/docs/en/sub-agents
```

## Verdict thresholds

| Score | Grade | Default verdict |
|------:|-------|-----------------|
| 90–100 | A | ship |
| 80–89  | B | ship |
| 65–79  | C | revise |
| 50–64  | D | revise |
| <50    | F | reject |

**Override:** any `critical` finding forces `verdict = reject` regardless of score. The score reflects overall quality; the verdict is the gate.

## Rubric

The canonical rubric lives at [`plugins/agents-team/lib/eval/rubric.md`](../plugins/agents-team/lib/eval/rubric.md). Every rule has a stable ID (`tool_hygiene.write_on_review_role`), severity, phase (static or judge), and a citation. Rules without citations go in `experimental/` and are off by default.

## CI integration

Add a step to your repo's CI:

```yaml
# .github/workflows/agent-quality.yml
name: agent-quality
on:
  pull_request:
    paths:
      - '.claude/agents/**'
      - '.claude/skills/**/SKILL.md'

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint changed agents
        run: |
          for f in $(git diff --name-only origin/${{ github.base_ref }}...HEAD -- '.claude/agents/*.md' '.claude/skills/**/SKILL.md'); do
            python3 plugins/agents-team/lib/eval/lint.py --strict "$f" || echo "::error file=$f::$(jq -r '.overall | "\(.grade) \(.score)/100 — \(.verdict)"' <<<"$(python3 plugins/agents-team/lib/eval/lint.py "$f")")"
          done
```

For the deep judge in CI, set `ANTHROPIC_API_KEY` in repo secrets and pass `--deep`. Cache hits keep cost bounded.

## Anti-goals

- Don't auto-rewrite agent files. Suggest fixes; the human applies.
- Don't score the agent's *generated artifacts* (code, copy). That's a different evaluator.
- Don't replace the LLM's own judgment on subjective trade-offs — the evaluator flags risks; humans pick.
- Don't add rubric items without a citation. Unsourced rules go in `experimental/` and are off by default.
- Don't couple to a single judge model. The judge model is swappable via `ANTHROPIC_JUDGE_MODEL`.

## Sources

- Anthropic Sub-agents — https://code.claude.com/docs/en/sub-agents
- Anthropic Skill best practices — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic *Demystifying evals for AI agents* — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- LangChain `agentevals` — https://github.com/langchain-ai/agentevals
- Braintrust agent eval framework — https://www.braintrust.dev/articles/ai-agent-evaluation-framework
- METR / AISI Inspect — https://evaluations.metr.org/elicitation-protocol/
- Galileo 2026 — https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks
- Instruction-Following Gap — https://arxiv.org/html/2601.03269 + https://arxiv.org/html/2510.03999v3
