# agents-team Evaluator Rubric

**Rubric version:** `1.0.0`

This is the canonical rule list the agents-team evaluator consumes. Every rule has a stable ID, a dimension, a severity, and a citation to either the Anthropic spec or published prior art. Rules without a citation go in `experimental/` and are off by default.

The static linter (`lib/eval/lint.py`) implements every rule that can be checked deterministically. The LLM-as-judge (`lib/eval/judge.py`) implements the rules that require nuance — description clarity, internal contradictions, role/tool mismatch, prompt-injection smell beyond regex. Both produce findings in the same v1 schema.

## How the judge consumes this rubric

For each dimension below, the judge runs **one isolated call** (per Anthropic + Braintrust + LangSmith convergent guidance). Each call:

1. Receives the agent / skill file plus the rubric items for that dimension.
2. Must quote the file as evidence **before** assigning a score.
3. Returns a per-dimension score 0–100, a list of findings (severity / rule / message / evidence / fix), and the model used.

The judge **does not** see all dimensions at once. Bundling dimensions loses isolation and degrades calibration.

## Dimensions and weights

| Dimension       | Weight (agent) | Weight (skill) |
|-----------------|---------------:|---------------:|
| frontmatter     | 0.15           | 0.20           |
| description     | 0.25           | 0.30           |
| tool_hygiene    | 0.15           | 0.10           |
| model_fit       | 0.10           | 0.05           |
| body_structure  | 0.20           | 0.25           |
| anti_patterns   | 0.15           | 0.10           |

---

## Dimension: `frontmatter`

| Rule ID | Severity | Phase | Question for judge / lint check |
|---------|----------|-------|---------------------------------|
| `frontmatter.name_missing` | critical | static | Is the `name` field present? Source: [Anthropic Sub-agents][sa] |
| `frontmatter.name_invalid_chars` | critical | static | Does `name` use only lowercase letters, digits, and hyphens? Source: [sa] |
| `frontmatter.name_too_long` | critical | static | If skill: is `name` ≤64 chars? Source: [Anthropic Skill best practices][sk] |
| `frontmatter.name_reserved` | critical | static | Does `name` avoid reserved prefixes (`anthropic-`, `claude-`)? Source: [sk] |
| `frontmatter.description_missing` | critical | static | Is `description` present? Source: [sa] |
| `frontmatter.description_too_long` | critical | static | If skill: is `description` ≤1024 chars? Source: [sk] |
| `frontmatter.model_retired` | warning | static | Does `model` reference a retired model family? Source: [sa] |
| `frontmatter.fields_unused_in_body` | suggestion | judge | Are all frontmatter fields referenced or honored by the body? An unused `memory: project` or `maxTurns: 50` is dead weight. |
| `frontmatter.cargo_cult_fields` | suggestion | judge | Are optional fields included only because other agents have them, or do they earn their place? |

[sa]: https://code.claude.com/docs/en/sub-agents
[sk]: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

---

## Dimension: `description`

| Rule ID | Severity | Phase | Question for judge / lint check |
|---------|----------|-------|---------------------------------|
| `description.length_outside_band` | warning | static | Is the agent description 80–400 chars? Source: [sa] |
| `description.first_or_second_person` | warning | static | Does description avoid "I help…" / "you can use…"? Source: [sk] |
| `description.no_use_when_trigger` | suggestion | static | Does description contain "use when/before/after/proactively/immediately" or "MUST BE USED"? Source: [sa] |
| `description.vague_verb_only` | warning | static | Does description avoid starting with `helps/assists/supports` alone? Source: [sa] |
| `description.routing_clarity` | warning | judge | Could a reader, knowing only this description, decide *not* to delegate to this agent on an out-of-scope task? If the description is so broad it pulls everything, score low. |
| `description.domain_specificity` | warning | judge | Does the description name a concrete domain noun (e.g. "TypeScript request handlers", not "code")? |
| `description.contradicts_body` | critical | judge | Does the description claim something the body contradicts (e.g. description says "read-only", body says it edits files)? |
| `description.misleading_proactive_trigger` | warning | judge | If the description claims "use proactively", does the role actually warrant proactive delegation, or would it constantly fire and waste cycles? |
| `description.terminology_consistent` | suggestion | judge | Does the description use the same domain terms as the body (no "request handler" in the description, "API endpoint" in the body)? Source: [sk] (consistent terminology rule) |

---

## Dimension: `tool_hygiene`

| Rule ID | Severity | Phase | Question for judge / lint check |
|---------|----------|-------|---------------------------------|
| `tool_hygiene.tools_omitted` | critical | static | Is `tools` (or `allowed-tools` for skills) explicitly set? Source: [sa] |
| `tool_hygiene.write_on_review_role` | critical | static | If name/description signals reviewer/auditor/linter/monitor: are write tools (Write/Edit/MultiEdit/NotebookEdit) absent? Source: [sa] |
| `tool_hygiene.bash_without_safeguard_on_readonly` | warning | static | If a read-only role has Bash, does it have `permissionMode` or a `PreToolUse` hook? Source: [sa] |
| `tool_hygiene.agent_tool_on_leaf` | suggestion | static | If `Agent` is granted, does the agent actually orchestrate? (Sub-agents cannot dispatch sub-agents.) Source: [sa] |
| `tool_hygiene.tool_purpose_alignment` | warning | judge | Does each granted tool have a justification implied by the body? An agent with `WebFetch` whose body never mentions external data is a smell. |
| `tool_hygiene.mcp_unjustified` | warning | judge | If MCP servers are granted in frontmatter, does the body reference them? Source: [sk] |
| `tool_hygiene.over_grant_for_simple_role` | warning | judge | Is the tool list larger than the role needs? E.g. a "format-the-readme" agent with `Bash`, `Glob`, `Grep`, `Agent`. |
| `tool_hygiene.under_grant_for_role` | warning | judge | Is the tool list missing tools the body clearly relies on? |

---

## Dimension: `model_fit`

| Rule ID | Severity | Phase | Question for judge / lint check |
|---------|----------|-------|---------------------------------|
| `model_fit.opus_on_readonly_role` | warning | static | Is Opus assigned to a role whose description signals read-only / lookup / triage? Source: [sa] |
| `model_fit.haiku_on_reasoning_role` | warning | static | Is Haiku assigned to a role whose description signals architecture / orchestration / multi-step reasoning? Source: [sa] |
| `model_fit.choice_justified` | suggestion | judge | If the model choice is non-default, does the body cite *why* in one line? |
| `model_fit.background_uses_haiku` | warning | judge | Is `background: true` paired with Haiku (cost-conscious for always-on monitors)? Source: [sa] |

---

## Dimension: `body_structure`

| Rule ID | Severity | Phase | Question for judge / lint check |
|---------|----------|-------|---------------------------------|
| `body_structure.no_when_invoked_section` | suggestion | static | Agent only: is there a `## When invoked` / procedure / workflow heading? Source: [sa] |
| `body_structure.no_constraints_section` | suggestion | static | Agent only: is there a `## Constraints` / guardrails / anti-patterns heading? Source: [sa] |
| `body_structure.skill_body_too_long` | warning | static | Skill only: is body <500 lines? Source: [sk] |
| `body_structure.skill_no_toc_when_long` | suggestion | static | Skill only: if body >100 lines, is there a TOC? Source: [sk] |
| `body_structure.has_quick_start` | suggestion | judge | Skill only: does the body show a minimal example in the first ~50 lines? Source: [sk] |
| `body_structure.examples_concrete` | suggestion | judge | Are examples concrete (input → output pairs), not abstract? Source: [sk] |
| `body_structure.workflow_numbered` | suggestion | judge | Are multi-step procedures numbered, not bulleted? Source: [sk] |
| `body_structure.feedback_loop_for_quality` | suggestion | judge | Skill only: does the body specify a validate → fix → repeat loop for quality-critical tasks? Source: [sk] |
| `body_structure.terminology_consistent` | suggestion | judge | Are domain terms (field/box/element/control, agent/specialist/teammate) used consistently? Source: [sk] |
| `body_structure.no_time_sensitive_language` | suggestion | judge | Are there phrases like "after August 2025" that will rot? Source: [sk] |
| `body_structure.solve_dont_punt` | warning | judge | Skill only: do bundled scripts handle errors rather than leaving them for Claude to resolve? Source: [sk] |
| `body_structure.role_responsibility_present` | warning | judge | Agent only: does the body open with a role line ("You are a senior X…") and a numbered procedure, matching the Anthropic reference pattern? Source: [sa] |

---

## Dimension: `anti_patterns`

| Rule ID | Severity | Phase | Question for judge / lint check |
|---------|----------|-------|---------------------------------|
| `anti_patterns.injection_system_tag` | warning | static | Body avoids embedded `<system>` tags? Source: [sa] |
| `anti_patterns.injection_ignore_prior` | warning | static | Body avoids "ignore prior/all/previous instructions"? Source: [sa] |
| `anti_patterns.injection_respond_only` | warning | static | Body avoids "respond only with…" override directives? Source: [sa] |
| `anti_patterns.hardcoded_absolute_path` | warning | static | Skill only: no hardcoded `/Users/...` or `C:\...`? Source: [sk] |
| `anti_patterns.body_says_readonly_tools_have_write` | critical | static | Body claims read-only but tools include write? Source: [sa] |
| `anti_patterns.subtle_role_drift` | warning | judge | Does the agent's body drift to handling tasks the description doesn't cover? E.g. description: "API engineer", body: "also touches frontend when needed". |
| `anti_patterns.deep_reference_chain` | suggestion | judge | Skill only: are referenced files >1 level deep from `SKILL.md`? Source: [sk] |
| `anti_patterns.competing_approaches_no_default` | suggestion | judge | Skill only: does the body present multiple approaches without a clear default? ("you can use pypdf, or pdfplumber, or PyMuPDF…") Source: [sk] |
| `anti_patterns.voodoo_constants` | suggestion | judge | Skill only: are bundled scripts free of unexplained magic numbers? Source: [sk] |
| `anti_patterns.contradictory_instructions` | critical | judge | Are there two passages that command opposite behavior (e.g. "always commit" + "never commit without permission")? Source: [sa] |

---

## Verdict thresholds

| Score band | Grade | Verdict (default) |
|-----------:|-------|-------------------|
| 90–100     | A     | `ship`            |
| 80–89      | B     | `ship`            |
| 65–79      | C     | `revise`          |
| 50–64      | D     | `revise`          |
| <50        | F     | `reject`          |

**Override:** any `critical` finding forces `verdict = reject` regardless of score (the score reflects overall quality; the verdict is the gate).

## Calibration target

Per Galileo 2026 guidance, the judge should achieve **≥0.80 Spearman correlation** with human raters on a 20-agent calibration set. The `lib/eval/calibration/` directory holds hand-graded fixtures. Run `lib/eval/calibrate.sh` after any rubric change to measure correlation; rubric changes that drop below 0.75 must be reviewed before merging.

(The calibration set is small in v0.1 — expanding it is a v0.2 issue.)

## Anti-goals (do not add)

- Style preferences without a citation (e.g. "always use Oxford commas") — those go in `--strict` mode only.
- Rules that score the *generated artifacts* an agent produces (code quality, copy quality). That is a different evaluator.
- Auto-rewriting the agent file. The evaluator suggests; the human applies.
- Rubric items that depend on a single judge model. Every rule must be model-agnostic; if a rule only fires reliably with Opus, it goes in `experimental/` until validated on Sonnet too.

## Sources

- Anthropic Sub-agents: https://code.claude.com/docs/en/sub-agents
- Anthropic Skill best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic *Demystifying evals for AI agents*: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- LangChain `agentevals`: https://github.com/langchain-ai/agentevals
- LangSmith trajectory evals: https://docs.langchain.com/langsmith/trajectory-evals
- Braintrust agent eval framework: https://www.braintrust.dev/articles/ai-agent-evaluation-framework
- METR / AISI Inspect: https://evaluations.metr.org/elicitation-protocol/
- Galileo 2026: https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks
- Instruction-Following Gap: https://arxiv.org/html/2601.03269 + https://arxiv.org/html/2510.03999v3
