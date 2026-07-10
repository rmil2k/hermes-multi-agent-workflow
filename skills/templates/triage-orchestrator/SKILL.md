---
name: triage-orchestrator
description: >
  Central orchestrator for the Hermes Multi-Agent Workflow.
  Picks up intake tasks, runs dedup/score/route, fans out research,
  proposes to the human gate, then drives post-gate fulfillment.
  This is the "brain" skill — installed on the orchestrator profile.
metadata:
  hermes:
    tags: [triage, orchestrator, core]
---

# Triage Orchestrator

> **Role:** The single stateful coordinator. Everything deterministic lives in
> `engine/`. This skill only does the parts that need model judgment:
> proposing scores, classifying research results, writing proposal prose,
> and deciding when to move items through the human gate.

## When it runs

- Triggered by new `intake` Kanban tasks (created by scouts)
- Also runs on a schedule to sweep for stuck items or new research results

## Core loop (one intake task)

1. Load the intake report (body of the Kanban task)
2. Parse candidates → call `hermes-triage` engine for each:
   - dedup
   - score
   - create item in vault
3. For items that pass threshold:
   - build research lane specs
   - create parallel research tasks (kanban)
4. When research completes → classify + route
5. Build prep specs → create prep tasks
6. Human gate (awaiting_approval)
7. On approval → build fulfillment specs → create fulfillment tasks
8. On delivery → mark item `delivered`, close chain

## Key invariants (do not break)

- **Never auto-approve.** Always stop at `awaiting_approval`.
- **Persistent `dir` workspaces** for all post-gate work (engine already enforces this).
- **One human notification** per item (use `hermes send`).
- First post-gate task must be `ready` (no parent).

## Commands it uses

```bash
hermes-triage validate
hermes-triage item show <slug>
hermes-triage item events <slug>
```

It also calls the engine programmatically when running inside Hermes.

## Output contract

The orchestrator writes:
- Research specs → Kanban tasks assigned to `researcher`
- Prep specs → Kanban tasks assigned to `analyst` / `builder`
- Fulfillment specs → Kanban tasks assigned to appropriate role
- Final delivery notification via `hermes send`

## Don't

- Don't implement scoring/routing/dedup logic here — use the engine.
- Don't bypass the human gate.
- Don't create tasks with blocking parents as the first post-gate step.