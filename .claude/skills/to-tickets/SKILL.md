---
name: to-tickets
description: Split remaining procurement requirements into independently verifiable vertical tickets with explicit blocking relationships.
---

Read docs/development-workflow.md and the source Issue body/comments plus current evidence.
For each remaining slice, specify Parent, What to build, Acceptance criteria and Blocked by.
Keep tickets small enough for one implementation context; include the required evidence type.
Reuse approved splits; confirm only new scope or materially changed dependencies.
Publish one issue per slice in blocker order, attach native sub-issue/blocking links when supported,
and use explicit links as a documented fallback. Preserve parent scope and state.
Completion: every remaining parent criterion has an owning ticket; no completed work is recreated.
