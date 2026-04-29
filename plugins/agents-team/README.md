# agents-team

Generate, meet with, and evaluate Claude Code agent teams.

## Install

```bash
# As a Claude Code plugin (path-based)
claude plugin install /path/to/agents-team/plugins/agents-team
```

## Skills

| Skill | What it does |
|-------|--------------|
| `/team-gen` | Generate a full agent team from a product description |
| `/meet` | Run a streamed multi-agent meeting on a topic; write minutes |
| `/evaluate-agent` | Static + LLM-judge quality evaluation of an agent or skill file |
| `/evaluate-agent-behavior` | Score an agent against transcripts and fixture prompts |

See the root [README.md](../../README.md) for the full project overview, and individual skill docs under `skills/<name>/SKILL.md`.
