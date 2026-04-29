# /meet — streamed multi-agent meeting

Gather every agent on the active team around a topic. Each speaks from their domain — constraint check, top 3 risks, dependencies, open questions, effort. The orchestrator consolidates to a global top-10, batches open questions for the client, and writes minutes to disk.

The skill is documented in [`plugins/agents-team/skills/meet/SKILL.md`](../plugins/agents-team/skills/meet/SKILL.md).

## When to run it

- Before approving a major plan in `.plans/`.
- After a significant client directive that reshapes the architecture.
- Before committing to a new service, tool, or vendor.
- When the orchestrator needs cross-domain consensus on a risk or trade-off.

## Quick path

```bash
# Inline topic
/meet "Should we ship the v2 migration this quarter?"

# Reference a plan file
/meet .plans/2026-04-29-payment-redesign.md
```

## What you get

A single Markdown file at `.meetings/YYYY-MM-DD-{topic-slug}.md`. If a meeting already exists for the same topic + date, the skill appends `-2`, `-3`, … rather than overwriting.

```markdown
# Meeting: Should we ship the v2 migration this quarter?

- Date: 2026-04-29
- Chaired by: shop-orch

## Recommendation
revise — payments migration risk too high without a backfill rehearsal

## Global top-10 risks (ranked)
1. Live cart state lost during cutover — raised by api-engineer, web-engineer
2. ...

## Disagreements
- security-engineer wants a 30-day soak; payments-engineer wants 7 days

## Open questions for client
Q1: What's the acceptable cart-loss rate during cutover?
Q2: ...

## Per-agent sections
### api-engineer
- Constraint check: pass — endpoints can shadow-write
- Top 3 risks: ...
...
```

## How it works

1. **Resolve the topic** — if it's a path under `.plans/` or `.requests/`, load it.
2. **Discover the team** — Glob `.claude/agents/*.md`. Skip `disable-model-invocation: true` and `background: true` agents (background monitors don't speak in meetings).
3. **Dispatch in parallel** — one `Agent` call per attendee, each with a fixed structured prompt.
4. **Stream** — each agent's response lands as it arrives; do not buffer.
5. **Consolidate** — global top-10 risks, disagreements, open questions, recommendation.
6. **Write** the minutes file. Print the path + recommendation as a one-liner.

## Cost expectations

- Wall-clock: 1–3 minutes for a 5-agent team; 5–10 minutes for a 15-agent team. Parallel dispatch keeps this bounded.
- Tokens: ~200 input + ~200 output per attendee, plus the orchestrator on top.

## Anti-patterns

- Treating one agent's view as the team's view — the whole point of `/meet` is the cross-domain check.
- Buffering all responses then dumping at the end — defeats streaming.
- Letting agents respond out-of-format — ask them to redo (one retry, then move on).
- Overwriting prior minutes — same topic + date appends `-N`, never overwrites.

## See also

- Built the team you're meeting with? [`docs/team-gen.md`](team-gen.md)
- Want to know if a specific agent is meeting-ready? [`docs/evaluator.md`](evaluator.md)
