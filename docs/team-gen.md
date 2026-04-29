# /team-gen — generator usage

Turn a product description into a complete `.claude/` agent team in one command. The generator picks archetypes, fills templates, scaffolds the directory structure, and runs the static linter on every produced file before exiting.

## Quick path

```bash
# 1. Hand the assistant a brief (file or inline). Try the bundled example:
/team-gen examples/example-prd.md --target .

# 2. Answer any clarifying questions (the skill asks, never invents)

# 3. Read the self-eval report at the bottom of the run
```

Or run the example end-to-end without the skill, straight from the spec:

```bash
python3 plugins/agents-team/lib/gen/scaffold.py \
  examples/example-team.json \
  --target /tmp/eshop-demo
```

See [`examples/README.md`](../examples/README.md) for the full walkthrough.

The skill is documented in [`plugins/agents-team/skills/team-gen/SKILL.md`](../plugins/agents-team/skills/team-gen/SKILL.md). What follows is the user-facing usage reference.

## What the brief should contain

The skill extracts these signals from a brief — give it whatever it needs to disambiguate:

| Signal               | Example                                              |
|----------------------|------------------------------------------------------|
| Domains / services   | "TypeScript API + React web + Stripe payments"       |
| Tech stack           | "Node 20, Postgres 16, deployed on Vercel"           |
| Team size hint       | "small team", "10–12 specialists", "lean MVP"        |
| Constraints          | "regulated", "multi-locale", "always-on monitor"     |

If the brief is sparse, the skill will ask via `AskUserQuestion`. Don't pre-fill defaults unless the user explicitly asks — the [no-quick-fixes rule](../plugins/agents-team/templates/rules/09-no-quick-fixes.md) applies to the generator too.

## Archetype catalog

8 agent archetypes, 4 skill archetypes — full list with frontmatter in [`plugins/agents-team/templates/agents/`](../plugins/agents-team/templates/agents/) and [`plugins/agents-team/templates/skills/`](../plugins/agents-team/templates/skills/).

| Archetype           | Model  | Notes                                                |
|---------------------|--------|------------------------------------------------------|
| `orchestrator`      | Opus   | Always include. Owns routing + plan lifecycle.        |
| `tech-leader`       | Opus   | Optional. Read-only architecture review.              |
| `domain-engineer`   | Sonnet | One per service / owned path.                         |
| `designer`          | Sonnet | Add when the product has a real UI.                   |
| `qa-engineer`       | Sonnet | Always include. `isolation: worktree`.                |
| `security-engineer` | Sonnet | Always include if auth / payments / PII / external.   |
| `devops-engineer`   | Sonnet | Add when the team owns CI/CD or infrastructure.       |
| `monitor`           | Haiku  | `background: true`. Add for ≥6 agents or "always-on". |

Skill archetypes (`domain-skill`, `coordination-skill`, `lint-skill`, `init-skill`) are templates the generator can drop in for team-specific commands like a daily status check or a per-service style guide.

## team.json spec

The skill assembles a `team.json` then hands it to `lib/gen/scaffold.py`. Format:

```json
{
  "team_name": "E-Shop",
  "services": ["api", "web", "payments"],
  "primary_locale": "en",
  "orchestrator": { "archetype": "orchestrator", "values": { "name": "shop-orch", "...": "..." } },
  "agents": [ { "archetype": "domain-engineer", "values": { "...": "..." } } ],
  "skills": [],
  "rules": ["01-plan-first", "03-definition-of-done", "13-model-selection"],
  "hooks": ["notify", "session-init", "teammate-idle-gate", "post-commit-check"]
}
```

Hand-edit if you want to regenerate with a tweaked spec. Saving it under `.claude/team.json` makes future regenerations one-shot.

## Self-eval gate

Every produced agent + skill is linted before the skill exits. A `reject` verdict on any file means the run failed, even if the rest passed. The exit code is the worst verdict observed.

```text
=== Self-evaluation ===
  shop-orch.md           A  100/100  ship
  api-engineer.md        A   97/100  ship
  qa-engineer.md         A  100/100  ship
=== Self-eval worst verdict: exit 0 ===
```

To skip the gate during iteration, pass `--no-self-eval`. Don't ship without it.

## Common patterns

**Lean MVP team (5 agents).** Orchestrator + 1 domain-engineer per service + qa + security. Skip devops + monitor until traffic justifies them.

**Regulated / payments team.** Always include `security-engineer`, the `12-security-vapt` rule, and a `monitor` to track auth-failure rates.

**Multi-frontend (web + mobile + desktop).** One `domain-engineer` per surface; consider a `designer` to keep the design system honest across them.

## Anti-patterns

- Two specialists with overlapping mandates. Merge them. The generator must enforce a clean delegation graph.
- Skipping the self-eval gate. It catches the mistakes you'll make at 2am.
- Auto-overwriting an existing `.claude/`. The skill always asks; archive `.claude.bak.YYYYMMDD/` first.
- Persona names baked in (e.g. "Tarek the API engineer"). Templates are deliberately de-personalized.

## See also

- Lint a single agent: [`docs/evaluator.md`](evaluator.md) → `/evaluate-agent`
- Hold a meeting on the generated team: [`docs/meet.md`](meet.md) → `/meet`
