---
description: "Defer unrelated requests. Don't drop current work because something else came up."
globs: "*"
alwaysApply: true
---

# Rule 5: Interrupt Handling

**When this applies:** every team.

When the user introduces a request unrelated to the in-progress task, **defer the new request** rather than abandon the current one.

## Procedure

1. Acknowledge the new request.
2. Save it as a deferred item — a request file (e.g. `.requests/YYYY-MM-DD-{slug}.md`), a `gh-pms` request issue, or a TODO list entry, depending on what the team uses.
3. Continue the current task. Do not switch unless the user explicitly asks you to abandon current work.
4. After current work reaches a stopping point, surface the deferred items.

## When to switch immediately

- The new request is explicitly marked urgent ("stop", "drop everything", "this is broken now").
- The new request is to *correct* the current work (e.g. "wait, do it differently").

In both cases, ask once to confirm rather than assume — switching context destructively is hard to reverse.
