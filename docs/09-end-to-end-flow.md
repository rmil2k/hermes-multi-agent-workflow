# End-to-End Flow (First Live Run)

This document describes the **first complete working flow** once the foundation + skills are installed.

## High-level flow

```
Scout (cron) → Intake Report + Kanban Task
          ↓
Orchestrator picks up intake
          ↓
Dedup → Score → Create Item (vault)
          ↓
Research fan-out (parallel lanes)
          ↓
Route + Prep specs
          ↓
Human gate (awaiting_approval)
          ↓
Fulfillment (post-gate)
          ↓
Delivery + notification
```

## Step-by-step

### 1. Scouts run on cron

- `triage-scout-x` runs at `:15` every hour on profile `xresearch`
- `triage-scout-web` runs at `:45` every hour on profile `webresearch`

Each scout:
- Searches its surface using the `query` from `triage.yaml`
- Writes a structured report to `vault/intake/`
- Creates **one** `intake` Kanban task on the `pain-point` board (assignee: `orchestrator`)

### 2. Orchestrator wakes up

The orchestrator profile has the `triage-orchestrator` skill installed.

When it sees a new `intake` task:
1. Reads the intake report (task body)
2. For each candidate:
   - Calls engine dedup
   - Scores the item
   - Creates item in `work/vault/items/<slug>.md`
   - Records events
3. For items above threshold:
   - Builds research specs (3 lanes)
   - Creates parallel research Kanban tasks (assignee: `researcher`)

### 3. Research phase

Researchers complete the 3 lanes:
- `verify_sources`
- `prior_context`
- `existing_solutions_audit`

Results are written back to the item vault (or attached to the research tasks).

### 4. Route + Prep

Orchestrator:
- Classifies research results
- Routes the item (`build` / `video` / `shelve`)
- Builds prep specs
- Creates prep tasks (assignee: `analyst` or `builder`)

### 5. Human gate

Item reaches status `awaiting_approval`.

Orchestrator sends a single notification (via `hermes send`) with:
- Item title + claim
- Score + breakdown
- Research summary
- Proposed path + next steps

Human replies with:
- `approve <slug>`
- `shelve <slug>`
- `re-research <slug>`

### 6. Post-gate fulfillment

On approval:
- Orchestrator builds fulfillment specs
- Creates fulfillment tasks with **persistent `dir` workspaces**
- Assigned to appropriate roles (`builder`, `tester`, `video_producer`, etc.)

### 7. Delivery

Final task in the chain:
- Marks item `delivered`
- Sends delivery notification
- Closes the Kanban chain

## Key invariants

- Scouts only detect (never dedup/score/route)
- Orchestrator is the only stateful long-running agent
- Human gate is **never** bypassed
- Post-gate work always uses persistent `dir` workspaces
- First post-gate task is always `ready` (no blocking parent)

## How to trigger the first run

After running:

```bash
hermes-triage scaffold --apply --skip-existing --base-profile default
```

Then:

1. Start the gateway on the orchestrator profile
2. Wait for the next scout cron (`:15` or `:45`)
3. Watch the `pain-point` board for the first `intake` task
4. Orchestrator will pick it up automatically

---

**Status:** Ready for first live end-to-end execution.