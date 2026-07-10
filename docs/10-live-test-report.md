# Live Test Report — Sub-Agent Chain

**Date:** 2026-07-10  
**Board:** `pain-point`  
**Status:** Successful live scout → orchestrator → researcher → analyst chain.

## What was fixed before the run

- Installed local skills directly into the target profile skill dirs because `hermes skills install <local path>` was interpreted as a registry fetch in this Hermes build.
- Verified skills are enabled in the correct profiles:
  - `triage-scout-web` in `webresearch`
  - `triage-scout-x` in `xresearch`
  - `triage-orchestrator` in `orchestrator`
- Created scout cron jobs with correct Hermes v0.17 syntax:
  - global `--profile` goes before `cron`, not inside `cron create`
- Hardened scout skill instructions to use `/opt/hermes/bin/hermes kanban --board pain-point create ...`.

## Live cron configuration

The profile-local scout crons were paused because profile gateways were not running, so they would not fire automatically. Reliable wrapper crons were installed in the default profile, whose gateway is already running.

Active default-gateway wrapper jobs:

- `52898226013b` — `triage-scout-web-wrapper`, schedule `45 * * * *`, script `triage_scout_web.sh`
- `e956bcd7337f` — `triage-scout-x-wrapper`, schedule `15 * * * *`, script `triage_scout_x.sh`

Wrapper scripts live under `/opt/data/scripts/` and invoke the scout profiles explicitly:

```bash
/opt/hermes/bin/hermes --profile webresearch --skills triage-scout-web chat -q "Run one web scout sweep now..."
/opt/hermes/bin/hermes --profile xresearch --skills triage-scout-x chat -q "Run one X scout sweep now..."
```

Paused profile-local jobs retained for reference:

- `1b4c90435f43` — `triage-scout-web` in profile `webresearch`
- `283215ef4396` — `triage-scout-x` in profile `xresearch`

## Manual live run

Command run:

```bash
/opt/hermes/bin/hermes --profile webresearch --skills triage-scout-web chat -q "Run one web scout sweep now. Follow the triage-scout-web skill exactly. Write the intake report and create one intake Kanban task on the pain-point board assigned to orchestrator."
```

Result:

- Intake report written:
  `/opt/data/profiles/webresearch/vault/intake/2026-07-10T203308Z-web.md`
- Kanban intake task created:
  `t_307f2d68 — intake: web 2026-07-10`

## Sub-agent chain observed

Final board state:

```text
✓ t_307f2d68  done      orchestrator          intake: web 2026-07-10
✓ t_16ddd23a  done      researcher            research: validate AI agent silent-failure pain point
✓ t_db81922e  done      analyst               synthesize: silent AI agent failure opportunity brief
```

### Orchestrator result

Task: `t_307f2d68`

Summary:

> Deduplicated the web intake into one clustered pain point around silent/semantic AI-agent failures and routed it through a research → synthesis pipeline. Created a researcher validation task and an analyst opportunity-brief task gated on the research output.

Created:

- `t_16ddd23a` — researcher validation task
- `t_db81922e` — analyst synthesis task

### Researcher result

Task: `t_16ddd23a`

Summary:

> Validated the AI-agent silent/semantic failure pain point. All 5 seed sources were accessible and quote-backed, with credibility caveats. Found 8 additional corroborating sources and produced a 13-row evidence table with exact quotes, pain-severity estimate, alternatives, opportunity assessment, and final recommendation.

Recommendation:

> PURSUE, but with a narrow wedge around semantic workflow assurance / client-impact detection rather than generic agent observability.

### Analyst result

Task: `t_db81922e`

Summary:

> Synthesized the parent silent-agent-failure research into a decision-ready opportunity brief. Recommendation is DEEPEN RESEARCH before build, with a gate-ready interview sprint and possible landing-page test if WTP/frequency validate.

Key handoff:

- Overall opportunity score: `3.9 / 5`
- Strongest fit: agent workflow reliability tooling
- Main gaps: hard prevalence, verified willingness-to-pay, service-business-specific proof, budget owner clarity
- Gate-ready next step: approve an 8–12 interview validation sprint; only run a landing-page test after interviews confirm urgency and WTP.

## Important follow-up hardening

The first run used scratch workspaces for researcher/analyst tasks. Hermes cleaned up the artifact files after completion. Logs and task summaries retained the content, but future useful artifacts must be written to persistent workspaces.

Action taken:

- Updated `triage-orchestrator` skill to require persistent `dir:` workspaces for child tasks.

Future follow-up task pattern:

```bash
/opt/hermes/bin/hermes kanban --board pain-point create "research: <title>" \
  --assignee researcher \
  --parent <intake-task-id> \
  --workspace dir:/opt/data/projects/hermes-multi-agent-workflow/work/items/<slug> \
  --body "<research spec>"
```

## Conclusion

The first live sub-agent chain worked end-to-end:

```text
web scout → intake task → orchestrator → researcher → analyst
```

The system is usable for live triage runs. The next improvement is persistence polish for generated artifacts and a human-gate notification task after analyst synthesis.
