---
name: code-review
description: Review changes from a fixed baseline with independent Standards and Spec agents before procurement delivery.
---

Read docs/development-workflow.md. Resolve the recorded baseline, capture
git diff <baseline>...HEAD and the commit list, and reject an empty or invalid scope.
Start two fresh, independent review agents, passing only baseline/head, diff command and sources:
- Standards: CLAUDE.md, CONTRIBUTING.md and applicable coding standards. Inspect clarity,
  duplication, naming, module boundaries and speculative abstractions; separate heuristics from violations.
- Spec: the child Issue and its relevant PRD/ADR criteria. Inspect omissions, wrong behavior,
  scope additions and whether the evidence actually satisfies acceptance.
Return actionable findings with locations and supporting requirements under separate axes.
Fix valid findings, rerun affected checks and re-review material changes.
Completion: both axes reviewed the delivered head and remaining findings are explicitly recorded.
