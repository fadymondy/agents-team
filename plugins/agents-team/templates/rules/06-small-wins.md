---
description: "Break work into the smallest deliverable that proves value. Ship that first."
globs: "*"
alwaysApply: true
---

# Rule 6: Small Wins

**When this applies:** every team.

Decompose every feature into the smallest deliverable that proves end-to-end value. Ship the small win first; iterate from there.

## What a small win looks like

- A read endpoint with two columns and one filter, before the full data model.
- One screen with hardcoded data, before wiring it to the backend.
- One agent's full behavior, before adding the second specialist.
- A linter that catches one rule, before the rule library.

## Why

- A live small win catches integration problems early.
- It exposes UX assumptions that mock-driven design hides.
- It gives the user something to react to, which is how scope sharpens.
- It avoids "10 things half-done" — the most common failure mode of large changes.

## Anti-patterns

- "Foundation first" sprawl — refactoring infrastructure for a feature that hasn't been validated.
- Stubbed end-to-end with no real data path — looks done but proves nothing.
- Long-lived branches that never reach main.
