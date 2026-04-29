---
name: meet
description: "Run a streamed multi-agent team meeting on a topic. Each agent speaks from their domain — constraint check, top risks, dependencies, open questions, effort. Orchestrator consolidates and writes minutes. Use before approving a plan, after a significant client directive, before committing to a new vendor or architecture, or when the team needs cross-domain consensus."
disable-model-invocation: false
user-invocable: true
argument-hint: "<topic-or-plan-file>"
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

# /meet — Streamed Team Roundtable

Gather the full agent roster around a topic. Each agent speaks from their domain, flags risks, and asks questions before implementation starts. Output is a consolidated minutes file written to `.meetings/YYYY-MM-DD-{topic-slug}.md`.

## Quick start

```bash
/meet "Should we ship the v2 migration this quarter?"
/meet .plans/2026-04-29-payment-redesign.md
```

## Procedure

1. **Resolve the topic.**
   - If the argument is a path to a file under `.plans/` or `.requests/`, load it. The minutes will reference this file.
   - Otherwise, treat the argument as a free-form topic string.
   - If no argument is given, ask the user what the meeting is about.

2. **Discover the team.**
   - Glob `.claude/agents/*.md` to find every agent file. Skip any agent with `disable-model-invocation: true` or `background: true` (background monitors don't speak in meetings).
   - Build the attendee list. Note who is missing — `/meet` should not silently exclude anyone.

3. **Dispatch agents in parallel** via the `Agent` tool, one Agent call per attendee. Each call uses the same prompt, customized only by the agent's name:

   > **Topic:** `{topic}` (file: `{plan_path}` if applicable)
   >
   > You are speaking at a `/meet` for {team_name}. Answer in this exact structure, ≤200 words total:
   >
   > 1. **Constraint check:** does the topic respect your domain's constraints? `pass` / `fail` / `n/a` + a one-sentence reason.
   > 2. **Top 3 risks:** ranked, each ≤25 words.
   > 3. **Needs from others:** which agents must do something for you to succeed?
   > 4. **Open questions:** what blocks your start? Phrase as questions for the client.
   > 5. **Effort:** dev-day estimate for your share — S (2) / M (3.5) / L (5) / XL (8) / XXL (13+).

4. **Stream each response** as it arrives. Do not buffer the whole roster before showing anything. Print each agent's answer under its own heading as the dispatch returns.

5. **Consolidate.** When every agent has spoken:
   - **Global top-10 risks** — sort all per-agent risks by severity-and-frequency. Tag each with the agent(s) who raised it.
   - **Disagreements** — flag any constraint check that came back `fail` or where two agents disagree about scope/order.
   - **Open questions for the client** — dedupe + batch.
   - **Recommendation** — `ship` / `hold` / `revise` / `delegate to sub-group`. State the reason in one sentence.

6. **Write minutes** to `.meetings/YYYY-MM-DD-{topic-slug}.md` using the template below. If the file already exists, append `-2`, `-3`, etc. — never overwrite.

7. **Report.** Print the file path + the recommendation as a one-liner so the user can act.

## Minutes template

```markdown
# Meeting: {Topic}

- **Date:** {YYYY-MM-DD}
- **Topic:** {topic string OR plan file path}
- **Chaired by:** {orchestrator name}

## Attendees

{name (role)} — present
{name (role)} — present
{name} — absent (background monitor)

## Recommendation

{ship | hold | revise | delegate} — {one-sentence reason}

## Global top-10 risks (ranked)

1. {risk} — raised by {agent(s)} — mitigation: {...}
2. ...

## Disagreements

- {what needs a client decision}

## Open questions for client

Q1: ...
Q2: ...

## Per-agent sections

### {Agent name} — {role}

- **Constraint check:** {pass | fail | n/a} — {reason}
- **Top 3 risks:**
  1. ...
  2. ...
  3. ...
- **Needs from others:** ...
- **Open questions:** ...
- **Effort:** {S | M | L | XL | XXL}

### ...
```

## Rules of the meeting

1. **Every agent must speak.** Silence is not consent. An agent that says "no concerns" must still state their effort estimate.
2. **Risks are ranked.** Top 3 from each agent. Orchestrator consolidates into a global top-10.
3. **Open questions go to the client.** Orchestrator batches them into one list at the end.
4. **No decisions without data.** If an agent doesn't know, they say so and propose what they'd measure.
5. **Effort is in dev-days.** S (2), M (3.5), L (5), XL (8), XXL (13+).

## When to use this skill

- Before approving a major plan file in `.plans/`.
- After a significant client directive that reshapes the architecture.
- Before committing to a new service, tool, or vendor.
- When the orchestrator needs cross-domain consensus on a risk or trade-off.

## Anti-patterns

- **Treating one agent's view as the team's view** — the whole point of `/meet` is the cross-domain check; do not skip the dispatch.
- **Buffering all responses then dumping at end** — defeats the streaming requirement; show each agent's answer as it lands.
- **Letting agents respond out-of-format** — the structured response is what makes consolidation possible. If an agent ignores the format, ask them to redo (one retry).
- **Overwriting prior minutes** — same topic same day = `-2` suffix, never overwrite.
- **Skipping background monitors silently** — note their absence in the Attendees list so the user knows the meeting was complete except for {name}.

## Output expectations

- Wall-clock cost: 1–3 minutes for a 5-agent team; 5–10 minutes for a 15-agent team. Parallel dispatch is what keeps this bounded.
- Token cost: ~200 input + 200 output per agent. Opus orchestrator on top.
- One Markdown file per meeting; auditable trail.
- Answers "is the team ready to start?" with evidence.
