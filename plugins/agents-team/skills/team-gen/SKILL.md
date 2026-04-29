---
name: team-gen
description: "Generate a complete Claude Code agent team (orchestrator + specialists, skills, rules, hooks) from a product description. Reads a PRD file or inline brief, picks archetypes, fills templates, writes to .claude/, and runs the static linter on every produced file before exiting. Use when a new project needs an agent team, when an existing team needs to be regenerated cleanly, or when scaffolding a fresh proof-of-concept."
disable-model-invocation: false
user-invocable: true
argument-hint: "<prd-file-or-inline> [--target <project-dir>] [--no-self-eval]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - TodoWrite
model: opus
effort: high
---

# /team-gen — Generate an agent team from a product description

This skill turns "build me a team" from a one-off craft into a measurable pipeline. It composes new teams from validated archetypes, then runs the evaluator on the result so you start with grade-A specialists, not whatever you happened to write at 2am.

## Quick start

```bash
# From a PRD file
/team-gen ./docs/product.md --target .

# Inline brief (you'll be asked clarifying questions)
/team-gen "An e-commerce backend with TypeScript API + React web + Stripe payments"

# Dry-run: show what would be generated, don't write
/team-gen ./docs/product.md --target . --dry-run
```

## Procedure

### 1. Parse the brief

- If the argument is a file path, read it.
- If inline, treat the string as the brief.
- Extract:
  - **Domains** (which services exist: api, web, mobile, payments, data, ml, devops, etc.)
  - **Tech stack** (TypeScript / Go / Python / Rust / Flutter, Postgres / Mongo, Vercel / GCP, etc.)
  - **Team size hint** (small = 4–6 specialists, default = 7–9, large = 10–12)
  - **Constraints** (regulated industry, multi-locale, always-on monitor needed, etc.)
- If anything is ambiguous, ask the user via `AskUserQuestion`. Do not invent.

### 2. Pick archetypes

Available agent archetypes in `plugins/agents-team/templates/agents/`:
- `orchestrator` — Opus, broad tools, delegates to all specialists
- `tech-leader` — Opus, read-only, architecture review
- `domain-engineer` — Sonnet, narrow whitelist, owns one path; instantiate one per domain
- `designer` — Sonnet, design system + UX
- `qa-engineer` — Sonnet, isolation: worktree
- `security-engineer` — Sonnet, read-mostly, OWASP focus
- `devops-engineer` — Sonnet, broad bash, smallest pipeline diffs
- `monitor` — Haiku, background: true, silent-by-default

Always include **orchestrator + qa-engineer + security-engineer**. Add specialists per detected domain. Add a `monitor` if the team is ≥6 agents or the brief mentions "always-on" / "production".

### 3. Pick rules

`plugins/agents-team/templates/rules/` has 13 numbered rule templates. Always include `01-plan-first`, `03-definition-of-done`, `04-clarify-unknowns`, `08-client-first-communication`, `09-no-quick-fixes`, `13-model-selection`. Add `02-service-boundaries` and `10-style-per-service` if there are 2+ services. Add `12-security-vapt` if the brief mentions auth, payments, PII, or external traffic.

### 4. Pick hooks

`plugins/agents-team/templates/hooks/` has `notify`, `session-init`, `teammate-idle-gate`, `post-commit-check`. Default to all four. The `settings.json.partial` wires them up.

### 5. Build a `team.json` spec

Write a JSON file at `<target>/.claude/team.json` (or `/tmp/team-gen-<timestamp>.json` for dry-run) with this shape:

```json
{
  "team_name": "<team-name>",
  "services": ["api", "web", "payments"],
  "primary_locale": "en",
  "orchestrator": {
    "archetype": "orchestrator",
    "values": {
      "name": "<team>-orch",
      "description": "<routing description, third person, includes 'use when' trigger>",
      "color": "#5B8DEF",
      "display_name": "<friendly name>",
      "role_title": "Routing & Sequencing",
      "specialists": "api-engineer, web-engineer, qa-engineer, security-engineer",
      "delegations": "API change → api-engineer\nWeb UI change → web-engineer\n..."
    }
  },
  "agents": [
    {
      "archetype": "domain-engineer",
      "values": {
        "name": "api-engineer", "description": "...", "color": "#22C55E",
        "display_name": "API Engineer", "domain": "API",
        "owned_paths": "services/api/",
        "primary_language": "TypeScript", "test_framework": "Vitest",
        "build_command": "pnpm --filter api build",
        "lint_command": "pnpm --filter api lint"
      }
    }
  ],
  "skills": [],
  "rules": ["01-plan-first", "03-definition-of-done", ...],
  "hooks": ["notify", "session-init", "teammate-idle-gate"]
}
```

Every agent value must be filled — descriptions in third person, `use when`/`use proactively`/`MUST BE USED` triggers present, names lowercase-hyphens. The static linter will flag misses.

### 6. Materialize

```bash
python3 plugins/agents-team/lib/gen/scaffold.py <team.json> --target <project-dir>
```

This:
- Creates `<target>/.claude/{agents,skills,rules,hooks}`.
- Renders archetype templates with each agent's values.
- Copies rules with `{{services}}` / `{{primary_locale}}` filled in.
- Copies hooks with `{{TEAM_NAME}}` filled in, marks them executable.
- Merges `settings.json.partial` into `<target>/.claude/settings.json`.
- Runs the static linter (`/evaluate-agent`) on every produced agent + skill — the **self-eval gate**.

The exit code is the worst verdict observed: `0` ship, `1` revise, `2` reject.

### 7. Read the self-eval report

If any agent comes back with `verdict: reject`, fix the offending values and re-run. Common fixes:
- Description too short / vague → expand to ≥80 chars with a `use when` clause.
- Reviewer role with `Edit` in tools → drop write tools.
- Body says read-only but tools include write → reconcile.

The whole point of the evaluator is that you don't ship a sub-par team because you forgot to put a use-when trigger in a description.

### 8. Idempotence

- If `<target>/.claude/agents/<name>.md` already exists, **ask before overwriting**. Use `AskUserQuestion`.
- If the user wants to regenerate cleanly, archive the old `.claude/` to `.claude.bak.YYYYMMDD-HHMMSS/` first.
- Re-running with the same team.json is safe (idempotent file writes).

## Output

```
Generated team for E-Shop at /Users/.../my-shop/.claude
  agents: 6
  skills: 1
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

## When to use this skill

- Brand-new project that needs a Claude Code agent team.
- Existing team where you want to regenerate cleanly from a refreshed PRD.
- Proof-of-concept where you want a team standing up in minutes.

## Anti-patterns

- **Inventing details the PRD doesn't specify.** If the user said "TypeScript backend" and didn't pick a framework, ask. Don't pick Express on their behalf.
- **Two specialists with overlapping mandates.** The generator must enforce a clean delegation graph. If `api-engineer` and `services-engineer` both say "owns the backend", merge them.
- **Skipping the self-eval gate.** It exists to catch the mistakes you'll make at 2am. `--no-self-eval` is for development only, not for shipping.
- **Auto-overwriting an existing team.** Always ask, archive first.
- **Persona names from sentra-hub or orch.** Templates are de-personalized. Keep them that way unless the user explicitly asks for personas.

## References

- Templates: `plugins/agents-team/templates/{agents,skills,rules,hooks}/`
- Renderer: `plugins/agents-team/lib/gen/render.py`
- Scaffolder: `plugins/agents-team/lib/gen/scaffold.py`
- Self-eval: `/evaluate-agent` (Phase 1 static linter)
- Sentra-hub layout (canonical reference for what "good" looks like): `/Users/fadymondy/Sites/sentra/sentra-hub/.claude/`
