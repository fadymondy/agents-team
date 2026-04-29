---
description: "Independent operations run in parallel. Sequential only when there is a real dependency."
globs: "*"
alwaysApply: true
---

# Rule 7: Parallel Execution

**When this applies:** every team. Especially relevant for orchestrators delegating to specialists.

If two operations have no data dependency, run them in parallel.

## Tool calls

When you can issue multiple tool calls in one message and the calls do not depend on each other's results (e.g. reading three files, running tests + lint, querying two endpoints), batch them into a single message with multiple tool blocks.

## Subagent delegation

When the orchestrator dispatches multiple specialists for independent subtasks, dispatch them concurrently — not in a serial loop. Concurrent dispatch is the difference between minutes and tens of minutes.

## When to stay sequential

- The output of one call feeds the next.
- The order matters for correctness (write before read of the same file).
- Concurrency would race on shared state (same DB row, same file path).

## Why

The user is waiting. Latency is the single biggest UX cost in agentic workflows. Two parallel 30-second calls cost 30 seconds; sequenced, they cost 60.
