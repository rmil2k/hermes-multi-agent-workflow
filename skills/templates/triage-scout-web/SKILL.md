---
name: triage-scout-web
description: >
  Web scout for the Hermes Multi-Agent Workflow.
  Searches the open web for candidate items matching the configured query,
  writes intake reports, and creates intake Kanban tasks.
metadata:
  hermes:
    tags: [triage, scout, web, intake]
---

# Triage Scout — Web

> **Source:** Web (general search / RSS / news)  
> **Profile:** webresearch (must have `kanban` toolset)

## What to look for

<!-- TODO: paste the actual `query` from triage.yaml sources[] entry -->
Find articles, posts, and discussions about AI agent workflows breaking silently, wasted hours, and blocked teams.

## Procedure

1. Search the web using the query above.
2. For each distinct candidate:
   - One-line **claim**
   - Source URLs (primary sources preferred)
   - Verbatim quote when possible
   - One line on **why it may matter**
3. Write report to:
   `${HERMES_PROFILE_DIR}/vault/intake/<UTC-timestamp>-web.md`
4. Create ONE intake Kanban task with the real Hermes CLI:
   ```bash
   /opt/hermes/bin/hermes kanban --board pain-point create "intake: web <UTC-date>" \
     --assignee orchestrator \
     --skill triage-orchestrator \
     --body "<path to the report>" \
     --created-by triage-scout-web
   ```

## Report format

```
source: web
captured_at: <UTC timestamp>

## Candidate: <title>
Claim: <one-line claim>
Sources:
  - url: https://...
    quote: "verbatim"
Why it may matter: <one line>
```

## Don't

- Don't dedup/score/route — that's the orchestrator.
- Don't fabricate sources.
- Don't post anywhere except the intake vault + one intake task.