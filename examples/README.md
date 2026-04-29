# Examples

A real, runnable example showing the generator end-to-end.

## What's here

- [`example-prd.md`](example-prd.md) — a sample product description (e-Shop SaaS). This is what `/team-gen` consumes.
- [`example-team.json`](example-team.json) — the team spec the generator builds from the PRD: 1 orchestrator + 8 specialists + 1 coordination skill + 13 rules + 4 hooks.

## Run it

```bash
# 1. From the repo root, scaffold the example team into a scratch directory:
mkdir -p /tmp/eshop-demo
python3 plugins/agents-team/lib/gen/scaffold.py \
  examples/example-team.json \
  --target /tmp/eshop-demo

# 2. Look at what was generated:
find /tmp/eshop-demo/.claude -type f | sort
```

You should see:

```text
/tmp/eshop-demo/.claude/agents/api-engineer.md
/tmp/eshop-demo/.claude/agents/mobile-engineer.md
/tmp/eshop-demo/.claude/agents/payments-engineer.md
/tmp/eshop-demo/.claude/agents/shop-designer.md
/tmp/eshop-demo/.claude/agents/shop-devops.md
/tmp/eshop-demo/.claude/agents/shop-orch.md
/tmp/eshop-demo/.claude/agents/shop-qa.md
/tmp/eshop-demo/.claude/agents/shop-security.md
/tmp/eshop-demo/.claude/agents/shop-watcher.md
/tmp/eshop-demo/.claude/agents/web-engineer.md
/tmp/eshop-demo/.claude/hooks/notify.sh
/tmp/eshop-demo/.claude/hooks/post-commit-check.sh
/tmp/eshop-demo/.claude/hooks/session-init.sh
/tmp/eshop-demo/.claude/hooks/teammate-idle-gate.sh
/tmp/eshop-demo/.claude/rules/01-plan-first.md
/tmp/eshop-demo/.claude/rules/02-service-boundaries.md
… (11 more rule files)
/tmp/eshop-demo/.claude/settings.json
/tmp/eshop-demo/.claude/skills/shop-status/SKILL.md
```

The scaffolder also runs the static linter on every produced agent + skill before exiting. You should see:

```text
=== Self-evaluation ===
  shop-orch.md           A  100/100  ship
  api-engineer.md        A   97/100  ship
  web-engineer.md        A  100/100  ship
  payments-engineer.md   A  100/100  ship
  mobile-engineer.md     A  100/100  ship
  shop-designer.md       A   97/100  ship
  shop-qa.md             A  100/100  ship
  shop-security.md       A  100/100  ship
  shop-devops.md         A  100/100  ship
  shop-watcher.md        A   98/100  ship
  shop-status.md         A   99/100  ship
=== Self-eval worst verdict: exit 0 ===
```

## Modify it

Want to see what happens if a description is too vague?

```bash
# Break one description on purpose:
python3 -c "
import json, sys
spec = json.load(open('examples/example-team.json'))
spec['agents'][0]['values']['description'] = 'Helps with code'
json.dump(spec, open('/tmp/eshop-broken.json','w'), indent=2)
"

# Generate; the linter catches it.
python3 plugins/agents-team/lib/gen/scaffold.py \
  /tmp/eshop-broken.json \
  --target /tmp/eshop-broken-out
```

The api-engineer's verdict will drop to `revise`, the run will exit nonzero, and the report will list `description.first_or_second_person` and `description.length_outside_band` as findings.

## Read more

- The full generator skill: [`docs/team-gen.md`](../docs/team-gen.md)
- The evaluator that runs the self-eval gate: [`docs/evaluator.md`](../docs/evaluator.md)
