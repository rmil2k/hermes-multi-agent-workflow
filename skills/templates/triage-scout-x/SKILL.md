---
name: triage-scout-x
description: >
  X/Twitter scout for the Hermes Multi-Agent Workflow.
  Searches X for candidate items matching the configured query,
  writes intake reports, and creates intake Kanban tasks.
metadata:
  hermes:
    tags: [triage, scout, x, intake]
---

# Triage Scout — X

> **Source:** X (Twitter)  
> **Profile:** xresearch (must have `kanban` toolset)

## What to look for

<!-- TODO: paste the actual `query` from triage.yaml sources[] entry -->
Find posts about AI agent workflows breaking silently, wasted hours, and blocked teams.

## Procedure

0. Verify X search access before the sweep. Prefer `xurl auth status` and `xurl search`; if `xurl` is missing, install it into the active profile/home PATH without handling secrets. If `xurl auth status` shows no registered app/token, do not attempt to register credentials inside an agent session. Write a blocked sweep report with the failed commands/errors and still create the single intake Kanban task pointing at that report.
1. Search X using the query above (respect rate limits).
2. For each distinct candidate:
   - One-line **claim**
   - Source URLs (tweet links)
   - Verbatim quote when possible
   - One line on **why it may matter**
3. Write report to:
   `${HERMES_PROFILE_DIR}/vault/intake/<UTC-timestamp>-x.md`
   Set `status: completed` only after a real X search succeeds. If access is
   unavailable, set `status: blocked`; the launcher preserves the report and
   escalation task but returns nonzero so monitoring cannot go false-green.
4. Create ONE intake Kanban task with the real Hermes CLI:
   ```bash
   /opt/hermes/bin/hermes kanban --board pain-point create "intake: x <UTC-date>" \
     --assignee orchestrator \
     --skill triage-orchestrator \
     --body "<path to the report>" \
     --created-by triage-scout-x
   ```

## Report format

```
source: x
captured_at: <UTC timestamp>
status: completed

## Candidate: <title>
Claim: <one-line claim>
Sources:
  - url: https://x.com/...
    quote: "verbatim"
Why it may matter: <one line>
```

## Don't

- Don't dedup/score/route — that's the orchestrator.
- Don't fabricate sources.
- Don't post anywhere except the intake vault + one intake task.