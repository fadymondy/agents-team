"""v0.1 regressions — bugs caught reactively that we never want to see again.

These three tests came directly from issues found during v0.1 implementation.
Marked `regression` so a future bisect / CI run can isolate them.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Regression 1: orchestrator with "report" in body falsely triggered
# tool_hygiene.write_on_review_role.
# ---------------------------------------------------------------------------
ORCHESTRATOR_REPORTING = """---
name: shop-orch
description: "Orchestrator for the e-Shop team. Use proactively at the start of any feature, bug, or cross-service question. Routes to api-engineer or web-engineer. MUST BE USED for cross-service tasks."
model: opus
color: "#5B8DEF"
memory: project
maxTurns: 50
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Agent
  - TodoWrite
effort: high
---

# Shop Orchestrator

## When invoked

1. Triage.
2. Pick a specialist.
3. Delegate.
4. **Synthesize** — when specialists return, integrate their output and **report back to the user**.

## Constraints

- Never push without permission.
"""


def test_regression_orchestrator_with_report_does_not_fire_write_on_review_role(lint, rule_ids):
    r = lint(ORCHESTRATOR_REPORTING)
    assert "tool_hygiene.write_on_review_role" not in rule_ids(r), (
        "Bug regressed: orchestrators that 'report back' to users were "
        "falsely flagged as reviewer roles."
    )


# ---------------------------------------------------------------------------
# Regression 2: monitor saying "cannot delegate" falsely triggered
# model_fit.haiku_on_reasoning_role via substring match on "delegate".
# ---------------------------------------------------------------------------
MONITOR_CANNOT_DELEGATE = """---
name: shop-watcher
description: "Background monitor for the e-Shop team. Watches activity log. Surfaces noteworthy events. Use proactively on every event."
model: haiku
color: "#A855F7"
memory: project
maxTurns: 5
background: true
tools:
  - Read
  - Glob
  - Grep
  - Bash
---

# Shop Watcher

## When invoked
1. Read events.

## Constraints
- Never write production code.
- Cannot edit files, push, or delegate to other agents.
"""


def test_regression_monitor_cannot_delegate_does_not_fire_haiku_on_reasoning(lint, rule_ids):
    r = lint(MONITOR_CANNOT_DELEGATE)
    assert "model_fit.haiku_on_reasoning_role" not in rule_ids(r), (
        "Bug regressed: 'cannot delegate' (negation) was matched as "
        "evidence of an architecture role and triggered Haiku-on-reasoning."
    )


# ---------------------------------------------------------------------------
# Regression 3: "Use before/after" was not recognized as a use-when trigger.
# ---------------------------------------------------------------------------
USE_BEFORE_TRIGGER = """---
name: shop-status
description: "Run a quick e-Shop status check across services. Use before /meet to set up the agenda."
disable-model-invocation: false
user-invocable: true
allowed-tools:
  - Read
  - Bash
model: haiku
---

# /shop-status

## Quick start
```bash
/shop-status
```

## What it does
1. Poll engineers.
"""


def test_regression_use_before_recognized_as_trigger(lint, rule_ids):
    r = lint(USE_BEFORE_TRIGGER, filename="SKILL.md")
    assert "description.no_use_when_trigger" not in rule_ids(r), (
        "Bug regressed: 'Use before/after' phrasing was not recognized "
        "as a use-when trigger."
    )
