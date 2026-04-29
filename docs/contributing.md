# Contributing to agents-team

The plugin is a small set of templates + a Python toolchain. Most contributions land in one of three places:

1. **A new archetype** (agent or skill template).
2. **A new rubric line-item** (rule the linter or judge should fire).
3. **A workflow tweak** (rule template, hook, scaffold behavior).

This guide covers all three.

## Project layout

```text
plugins/agents-team/
  .claude-plugin/plugin.json    manifest
  agents/                       plugin's own subagents (rare)
  skills/                       /team-gen, /meet, /evaluate-agent, /evaluate-agent-behavior
  rules/                        plugin-internal rules (rare)
  hooks/                        plugin-internal hooks (rare)
  templates/                    archetypes the generator emits
    agents/                       8 archetypes
    skills/                       4 archetypes
    rules/                        13 numbered rule templates
    hooks/                        notify, idle-gate, session-init, post-commit
    fixtures/                     filled-in example agents/skills (used in tests)
    eval-fixtures/                known-good / known-bad for the linter
  lib/
    eval/                       static linter, judge skeleton, replay grader, schema, rubric
    gen/                        template renderer, scaffolder
docs/                            user-facing docs (you're reading one)
```

## gh-pms workflow

Issues are tracked under [github.com/fadymondy/agents-team/issues](https://github.com/fadymondy/agents-team/issues). The repo uses [gh-pms](https://github.com/fadymondy/gh-pms) labels (`type:*`, `status:*`, `severity:*`, `effort:*`, `svc:*`).

Standard flow:

1. Pick an open `status:todo` issue (or file a new `type:feature` / `type:bug`).
2. Move it to `status:in-progress` (`/gh-pms:gh-current` or `gh issue edit ... --add-label status:in-progress`).
3. Work on a feature branch. Commit messages reference the issue (`Closes #N`).
4. Push and open a PR.
5. After merge, the issue auto-closes.

Plan-first: any change touching 2+ files or crossing a service boundary needs a plan in `.plans/YYYY-MM-DD-{slug}.md` before code lands. See [rule 01](../plugins/agents-team/templates/rules/01-plan-first.md).

## Add a new archetype

Steps:

1. Add the template under `plugins/agents-team/templates/agents/<name>.md.template` (or `templates/skills/`).
2. Use `{{placeholders}}` for values the generator will fill — see [`render.py`](../plugins/agents-team/lib/gen/render.py).
3. Add a filled-in fixture under `templates/fixtures/example-<name>.md`.
4. Run the static linter on the fixture: `python3 plugins/agents-team/lib/eval/lint.py templates/fixtures/example-<name>.md`. The fixture must produce **0 critical findings**.
5. Update [`docs/team-gen.md`](team-gen.md)'s archetype catalog table.
6. Update [`skills/team-gen/SKILL.md`](../plugins/agents-team/skills/team-gen/SKILL.md) — add a one-liner under "Available agent archetypes".
7. Open a PR with `Closes #N` referencing the issue you started from.

## Add a new rubric line-item

Every rule has to cite a source. No exceptions for the canonical rubric — unsourced rules go in `experimental/` and are off by default.

Steps:

1. Pick the dimension (`frontmatter`, `description`, `tool_hygiene`, `model_fit`, `body_structure`, `anti_patterns`).
2. Decide the phase: `static` (deterministic, regex / structure check) or `judge` (LLM nuance).
3. Write the rule entry in [`lib/eval/rubric.md`](../plugins/agents-team/lib/eval/rubric.md) — stable ID (`<dim>.<rule>`), severity, phase, prompt for the judge / lint check, citation URL.
4. If `static`: implement the rule function in [`lib/eval/lint.py`](../plugins/agents-team/lib/eval/lint.py) under the matching `@rule("<dim>")` decorator. Each function yields zero or more `Finding` objects.
5. If `judge`: it's automatically picked up by `judge.py` from the rubric — no code change needed.
6. Add a known-bad fixture at `templates/eval-fixtures/known-bad/<rule>.md` that exercises the rule. The linter must produce a finding with the matching ID.
7. Run the full smoke test:

   ```bash
   for f in plugins/agents-team/templates/eval-fixtures/known-bad/*.md; do
     python3 plugins/agents-team/lib/eval/lint.py "$f"
   done
   ```

8. Update the calibration set if you've changed how an existing rule fires (Galileo 0.80 Spearman target).

## Add a new rule template

These are the per-team rules `/team-gen` drops into `.claude/rules/`. They are **not** the same as evaluator rubric items.

Steps:

1. Pick a slot. Numbers go up; reuse an existing number only if you're replacing it. Current span: `01..13`.
2. Add `templates/rules/NN-<kebab>.md` with frontmatter `description` + the body. Open with `**When this applies:**` so the generator can pick a subset by domain.
3. Update [`docs/team-gen.md`](team-gen.md) → "Pick rules" if the rule is part of a default set.
4. Reference any new placeholders (`{{services}}`, `{{primary_locale}}`, …) so the scaffolder can fill them.

## Add a new hook

Hooks fire from Claude Code on events like `SessionStart`, `Notification`, `Stop`, `TaskCompleted`, `TeammateIdle`.

Steps:

1. Add `templates/hooks/<name>.sh`. Use `{{TEAM_NAME}}` for placeholders.
2. Make it executable (`chmod +x`).
3. Wire it in `templates/hooks/settings.json.partial` so the scaffolder merges it into the generated team's `settings.json`.
4. Run a syntax check: `bash -n templates/hooks/<name>.sh`.

## Run the test suite

There isn't a formal test suite yet — instead, the contract is:

- `python3 lib/eval/lint.py templates/fixtures/<any>.md` passes.
- `python3 lib/eval/lint.py templates/eval-fixtures/known-bad/<any>.md` produces the expected critical / warning rule.
- `python3 lib/gen/scaffold.py /tmp/spec.json --target /tmp/test-output` exits 0 with all generated agents at A-grade.
- `bash -n` passes on every shell script under `templates/hooks/` and `lib/eval/`.

A formal pytest layer is a v0.2 issue.

## Style

- **Python** — stdlib only; no `pyyaml`, no `requests`, no `click`. The frontmatter parser is deliberately a regex sub.
- **Bash** — works under bash 3.2 (macOS default) and bash 5+ (Linux). No `set -u` if you can avoid it; tests have shown it bites with empty arrays.
- **Markdown** — third-person descriptions in skills; numbered procedures in agents; cite sources for any rule.
- **Comments** — only when the *why* is non-obvious. The code's *what* should be obvious from naming and structure.

## Release ritual

Releases are tagged `v<MAJOR>.<MINOR>.<PATCH>` and follow [Semantic Versioning](https://semver.org/). The `plugin.json` version is the source of truth: a release commit bumps it from `<X.Y.Z>-dev` to `<X.Y.Z>`, the commit is tagged, and a follow-up commit bumps to `<X.Y+1.0>-dev` so "is this a release build?" is answerable from the manifest alone.

Procedure:

```bash
# 1. Verify CHANGELOG.md has a polished section for the upcoming version
#    (the auto-changelog workflow keeps [Unreleased] up to date).
# 2. Bump the manifest:
sed -i '' 's/"version": "0\.X\.Y-dev"/"version": "0.X.Y"/' plugins/agents-team/.claude-plugin/plugin.json
git add plugins/agents-team/.claude-plugin/plugin.json
git commit -m "chore(release): v0.X.Y"

# 3. Tag and push:
git tag -a v0.X.Y -m "v0.X.Y — <one-line summary>"
git push origin main
git push origin v0.X.Y

# 4. The release.yml workflow auto-creates the GitHub Release with notes
#    extracted from CHANGELOG.md via git-cliff --latest. No manual step.

# 5. Bump to next dev:
sed -i '' 's/"version": "0\.X\.Y"/"version": "0.X+1.0-dev"/' plugins/agents-team/.claude-plugin/plugin.json
git add plugins/agents-team/.claude-plugin/plugin.json
git commit -m "chore: post-release bump to 0.X+1.0-dev"
git push
```

Tag style is `vX.Y.Z` (with the `v`), matching git-cliff's default tag pattern in `cliff.toml`.

## License

MIT. By submitting a PR you agree your contribution is licensed under the same terms.
