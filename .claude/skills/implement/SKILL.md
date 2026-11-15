---
name: implement
description: Complete one ready procurement ticket through focused implementation, behavior verification and independent review.
disable-model-invocation: true
---

Read docs/development-workflow.md and fetch the chosen ticket. State its title and baseline SHA.
Use an isolated codex/ branch from current origin/main and preserve unrelated work.
Reproduce existing behavior before changing it. For a confirmed gap, use a failing public-boundary
test followed by the smallest implementation; use existing approved testing boundaries.
Run targeted tests during work, then lint, full offline regression and release gate.
Commit the milestone and read code-review for an independent review of baseline...HEAD.
Fix valid findings and rerun affected checks before ship.
Completion: all ticket evidence is present, or the unmet criteria are explicitly left open.
