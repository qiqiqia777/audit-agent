---
name: ship
description: Ship a verified milestone through a development branch and pull request with review evidence and current CI.
---

Read docs/development-workflow.md before shipping; it owns completion and merge rules.

1. Run Ruff and the release gate (Makefile or equivalent Python commands). Record skipped judge/live tests honestly.
2. Inspect status and diff. Stage only intended files; keep secrets and runtime data local.
3. Commit a specific subject and a body explaining why and what verification passed. Use truthful attribution.
4. Push the current codex/ branch, then create/update its PR against main.
5. Include Ticket/requirements, Baseline/Head, Standards/Spec review and fixes, validation by evidence type, and remaining limitations.
6. Wait for checks on the PR's latest head SHA. Repair failures and verify the new head.
7. Apply the project's merge/completion rules. Keep unmet acceptance items open and report the PR URL.
