---
description: "Never push code or open PRs without explicit user permission."
globs: "*"
alwaysApply: true
---

# Rule 11: No Push Without Permission

**When this applies:** every team.

`git commit` is local — you may freely commit your work. `git push`, opening PRs, force-pushing, or any action that touches the remote requires **explicit user permission**.

## Procedure

- Make commits as you go (with clear messages).
- When the work is ready, summarize and **ask** before pushing: "Ready to push to `feat/foo`?"
- For PRs: ask before opening one. The user often wants to read the diff locally first.
- For force-push, branch deletion, or anything that rewrites remote history: always ask, even if you got "ok to push" earlier.

## Exception

If the team's CLAUDE.md explicitly authorizes pushing for a specific branch or workflow (e.g. a long-running automation branch), respect that scope and do not push outside it.

## Why

A push is visible and creates pressure on reviewers. A bad push is hard to retract (force-push has its own dangers; cherry-picking out is messy). Asking takes seconds; cleaning up doesn't.
