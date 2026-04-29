---
name: shop-status
description: "Run a quick e-shop status check across services — ask each engineer for one-line health and surface blockers. Use proactively at the start of a work session."
disable-model-invocation: false
user-invocable: true
argument-hint: "[--services svc1,svc2]"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Agent
  - TodoWrite
model: opus
effort: high
---

# /shop-status — Daily Team Status

Quickly poll every engineer for a one-line health report and surface anything blocking.

## Quick start

```bash
/shop-status
/shop-status --services api,web
```

## What it does

1. **Pick the engineers to poll** — default: all; with `--services`, only the specified services' owners.
2. **Dispatch in parallel** — one `Agent` call per engineer, each with the same prompt: "1 line: what are you doing today, and any blockers?"
3. **Collate** — wait for all responses; group by status (working / blocked / idle).
4. **Persist output** — writes to `.meetings/YYYY-MM-DD-status.md`.

## Output shape

A short Markdown file with:

- One section per engineer: name, current focus, blocker (if any).
- A "Top blockers" summary, sorted by severity.
- A "Suggested next move" line from the orchestrator.

## When to use this skill

- Start of the work session.
- After a long meeting where context was lost.
- Before a `/meet` to set up the agenda.

## Anti-patterns

- Calling `/shop-status` in a loop — it costs an Agent call per engineer.
- Treating the output as a substitute for `/meet` — it captures status, not decisions.

## Streaming

This skill streams partial output as each engineer responds — do not buffer the whole run before showing anything to the user.
