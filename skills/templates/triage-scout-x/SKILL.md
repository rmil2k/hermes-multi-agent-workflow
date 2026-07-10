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

1. Search X using the query above (respect rate limits).
2. For each distinct candidate:
   - One-line **claim**
   - Source URLs (tweet links)
   - Verbatim quote when possible
   - One line on **why it may matter**
3. Write report to:
   `${HERMES_PROFILE_DIR}/vault/intake/<UTC-timestamp>-x.md`
4. Create ONE intake Kanban task:
   ```bash
   kanban_create(
     board: "<board from triage.yaml>",
     title: "intake: x <UTC-date>",
     assignee: "orchestrator",
     body: "<path to the report>"
   )
   ```

## Report format

```
source: x
captured_at: <UTC timestamp>

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