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
- **Persistent `dir` workspaces** for every child task that writes useful artifacts — research, analysis, prep, and fulfillment. Do not rely on scratch workspaces; Hermes cleans them up after completion.
- Use a stable per-item workspace such as `/opt/data/projects/hermes-multi-agent-workflow/work/items/<slug>/` and create child tasks with `--workspace dir:/opt/data/projects/hermes-multi-agent-workflow/work/items/<slug>`.
- **One human notification** per item (use `hermes-triage gate notify --apply`, which wraps `hermes send`).
- First post-gate task must be `ready` (no parent).

## Commands it uses

```bash
hermes-triage validate
hermes-triage item show <slug>
hermes-triage item events <slug>
hermes-triage gate notify --file <proposal.md> --subject "[gate] <slug>" --apply
hermes-triage gate handle --reply "approve <slug>"
```

It also calls the engine programmatically when running inside Hermes.

## Output contract

The orchestrator writes:
- Research specs → Kanban tasks assigned to `researcher`, with persistent `dir:` workspace
- Prep/spec synthesis tasks → Kanban tasks assigned to `analyst` / `builder`, with persistent `dir:` workspace
- Fulfillment specs → Kanban tasks assigned to appropriate role, with persistent `dir:` workspace
- Human-gate proposal notification via `hermes-triage gate notify --apply`
- Final delivery notification via `hermes send`

## Human gate notification

When prep is complete, write the proposal markdown into the item's persistent path workspace, set the item status to `awaiting_approval`, then send the proposal through the configured gate target:

```bash
hermes-triage gate notify \
  --file /opt/data/projects/hermes-multi-agent-workflow/work/<path-subdir>/<slug>/proposal.md \
  --subject "[human gate] <slug>" \
  --apply
```

The target comes from `triage.yaml`:

```yaml
gate:
  channel: discord
  target: discord:rmil2k
```

If `target` is omitted, the helper sends to the channel/platform home target named by `channel` (for example `discord`).

When creating follow-up tasks manually, use this pattern:

```bash
/opt/hermes/bin/hermes kanban --board pain-point create "research: <title>" \
  --assignee researcher \
  --parent <intake-task-id> \
  --workspace dir:/opt/data/projects/hermes-multi-agent-workflow/work/items/<slug> \
  --body "<research spec>"
```

## Don't

- Don't implement scoring/routing/dedup logic here — use the engine.
- Don't bypass the human gate.
- Don't create tasks with blocking parents as the first post-gate step.