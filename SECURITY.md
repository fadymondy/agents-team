# Security policy

## Reporting a vulnerability

If you discover a security issue in `agents-team`, please **do not** open a public GitHub issue.

Email **<info@3x1.io>** with the subject line `agents-team security: <one-line summary>`. Include:

- The affected version (`plugin.json` `version` field).
- A clear description of the issue and the impact.
- Reproduction steps or a proof-of-concept.
- Any suggested mitigation, if you have one.

## Response window

- Acknowledgement within **3 business days**.
- Triage + initial assessment within **7 business days**.
- Fix or mitigation timeline communicated as part of triage.

## Disclosure policy

- We follow **coordinated disclosure**. We ask that you do not publicly disclose details until a fix has shipped or **90 days** have passed since the report, whichever comes first.
- Once fixed, the advisory will be published under the repo's [Security Advisories](https://github.com/fadymondy/agents-team/security/advisories), with credit to the reporter (unless they request anonymity).

## Scope

In scope:

- Vulnerabilities in the plugin code (`lib/eval/`, `lib/gen/`, hooks, skills).
- Generated team artifacts whose templates would propagate the vulnerability to downstream users.
- Dependency CVEs in pinned versions, where exploitation is plausible.

Out of scope:

- Vulnerabilities in Claude Code itself — report those to Anthropic via their channels.
- Vulnerabilities in *user-supplied* PRDs or `team.json` files. Treat user input as untrusted; the plugin does not execute it.

## Security best practices for users

- Do not paste credentials or PII into prompts the generator processes.
- Do not run `/evaluate-agent-behavior --live` against production credentials. Use sandboxed env + fixtures (see `docs/evaluator.md`).
- Pin your plugin install to a tagged release rather than `main`.
