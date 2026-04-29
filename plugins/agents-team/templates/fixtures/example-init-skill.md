---
name: shop-init
description: "First-time setup for the e-shop dev environment. Detects what is already provisioned (env vars, dependencies, database, secrets), provisions what is missing, and prints a status report. Idempotent — safe to re-run."
disable-model-invocation: true
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
model: sonnet
---

# /shop-init — First-time setup

## Quick start

```bash
/shop-init
```

## What it does

1. **Detect state** — read `.env.local`, `package.json`, `pnpm-lock.yaml`, the local Postgres, the secret store; figure out what is already set up.
2. **Provision the missing** — write a sane `.env.local` from `.env.example`, run `pnpm install`, run database migrations, prompt for any secrets that have no default.
3. **Print a status report** — what was already there, what was added, what the user should do next (e.g., "run `/shop-status` to verify all services start").

## State checks

- `.env.local` exists and contains required keys
- `node_modules/` exists and matches the lockfile
- Postgres is reachable on the configured port
- Required secrets are present in the secret store

## What it provisions

- `.env.local` populated from `.env.example` (asks before overwriting an existing one)
- `pnpm install --frozen-lockfile`
- Database migrations: `pnpm --filter api migrate up`
- Seed data via `pnpm --filter api seed:dev`

## When to use this skill

- First-time team setup on a new machine.
- After cloning the repo to a new dev environment.
- After an upgrade that adds a new required artifact (env var, migration, dep).

## Anti-patterns

- Overwriting an existing `.env.local` without asking — always diff and confirm.
- Re-running and producing duplicates — every step is idempotent and bails early if the state is already correct.
- Running this in CI — it is for human dev environments. CI bootstrap is in `.github/workflows/ci.yml`.
