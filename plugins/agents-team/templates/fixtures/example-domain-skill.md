---
name: shop-deploy
description: "Run a controlled deploy of the e-shop services. Picks the changed service, validates the manifest, dry-runs the deploy, then ships to staging and (with confirmation) prod. Use when the user says deploy, ship, release, push to prod for one of the e-shop services."
disable-model-invocation: false
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
model: sonnet
---

# /shop-deploy — Controlled deploy

Ships changes to one e-shop service per invocation. Validates the manifest, dry-runs the deploy against the target environment, then applies. Always staging before prod.

## Quick start

```bash
/shop-deploy api --to staging
/shop-deploy web --to prod    # asks for confirmation before applying
```

## When to use this skill

- After a feature merges to `main` and needs to land in staging.
- When promoting a tested staging build to prod.
- After a hot-fix needs an out-of-cycle ship.

## Patterns

### Pre-flight check

Verify the target environment is reachable, the image tag exists in the registry, and no other deploy is in flight (`kubectl get deployments` shows no in-progress rollouts).

### Dry-run first

Always run `kubectl apply --dry-run=server` before the real apply. Surface the diff to the user. If the diff is non-trivial, hand off to shop-devops for review before proceeding.

### Rollback plan

Every successful apply records the previous revision in `deploy-log/<service>.jsonl`. Rolling back is `kubectl rollout undo deployment/<service>`. Document this in the PR before deploying.

## Anti-patterns

- Deploying directly to prod without staging passing.
- Skipping the dry-run "to save time" — it costs seconds and prevents the only kind of incident that takes hours to fix.
- Long-lived stuck rollouts left running while you context-switch.

## References

- `deploy/<service>/manifest.yaml` — the source-of-truth manifests
- `/shop-status` — pre-deploy team status check
