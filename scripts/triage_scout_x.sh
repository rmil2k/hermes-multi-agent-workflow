#!/usr/bin/env bash
# Fail-closed launcher for the paused X scout cron.
set -euo pipefail

HERMES_BIN="${HERMES_BIN:-/opt/hermes/bin/hermes}"
TRIAGE_X_PROFILE="${TRIAGE_X_PROFILE:-xresearch}"
TRIAGE_X_SKILL="${TRIAGE_X_SKILL:-triage-scout-x}"
TRIAGE_X_BOARD="${TRIAGE_X_BOARD:-pain-point}"
TRIAGE_X_WORKDIR="${TRIAGE_X_WORKDIR:-/opt/data/projects/hermes-multi-agent-workflow}"
TRIAGE_X_INTAKE_DIR="${TRIAGE_X_INTAKE_DIR:-/opt/data/profiles/xresearch/vault/intake}"
export HERMES_HOME="${HERMES_HOME:-/opt/data}"

cd "$TRIAGE_X_WORKDIR"
mkdir -p "$TRIAGE_X_INTAKE_DIR"

before_reports="$(mktemp)"
before_tasks="$(mktemp)"
after_tasks="$(mktemp)"
agent_log="$(mktemp)"
cleanup() { rm -f "$before_reports" "$before_tasks" "$after_tasks" "$agent_log"; }
trap cleanup EXIT

python3 - "$TRIAGE_X_INTAKE_DIR" >"$before_reports" <<'PY'
import json
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
print(json.dumps(sorted(str(path.resolve()) for path in root.glob("*-x.md") if path.is_file())))
PY

if ! "$HERMES_BIN" --profile "$TRIAGE_X_PROFILE" kanban --board "$TRIAGE_X_BOARD" list --json >"$before_tasks"; then
  echo "triage-scout-x: unable to snapshot Kanban tasks before run" >&2
  exit 69
fi

set +e
"$HERMES_BIN" --profile "$TRIAGE_X_PROFILE" --skills "$TRIAGE_X_SKILL" chat -q \
  "Run one X scout sweep now. Follow the triage-scout-x skill exactly. Write the intake report and create one intake Kanban task on the ${TRIAGE_X_BOARD} board assigned to orchestrator." \
  2>&1 | tee "$agent_log"
agent_rc=${PIPESTATUS[0]}
set -e

if (( agent_rc != 0 )); then
  echo "triage-scout-x: Hermes agent failed with exit ${agent_rc}" >&2
  exit "$agent_rc"
fi

# Hermes v0.17 can print a terminal provider/model failure while returning zero.
if grep -Eiq 'API call failed|model_not_found|provider/model failure|Non-retryable (client )?error|Error: HTTP [45][0-9][0-9]|Traceback \(most recent call last\)' "$agent_log"; then
  echo "triage-scout-x: provider/model failure detected despite zero Hermes exit" >&2
  exit 70
fi

report_path="$(python3 - "$TRIAGE_X_INTAKE_DIR" "$before_reports" <<'PY'
import json
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
before = set(json.loads(pathlib.Path(sys.argv[2]).read_text()))
after = sorted(str(path.resolve()) for path in root.glob("*-x.md") if path.is_file())
new = [path for path in after if path not in before]
if len(new) != 1:
    raise SystemExit(1)
print(new[0])
PY
)" || {
  echo "triage-scout-x: no new X intake report (or more than one was created)" >&2
  exit 71
}

if ! grep -Eq '^source:[[:space:]]*x[[:space:]]*$' "$report_path" || \
   ! grep -Eq '^captured_at:[[:space:]]*[^[:space:]]+' "$report_path" || \
   ! grep -Eq '^status:[[:space:]]*(completed|blocked)[[:space:]]*$' "$report_path"; then
  echo "triage-scout-x: new report is missing source: x, captured_at, or valid status" >&2
  exit 72
fi

if grep -Eq '^status:[[:space:]]*blocked[[:space:]]*$' "$report_path"; then
  blocked_sweep=1
else
  blocked_sweep=0
fi

if ! "$HERMES_BIN" --profile "$TRIAGE_X_PROFILE" kanban --board "$TRIAGE_X_BOARD" list --json >"$after_tasks"; then
  echo "triage-scout-x: unable to verify Kanban tasks after run" >&2
  exit 73
fi

if ! python3 - "$before_tasks" "$after_tasks" "$report_path" <<'PY'
import json
import pathlib
import sys


def tasks(path):
    value = json.loads(pathlib.Path(path).read_text())
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("tasks", "items", "results"):
            if isinstance(value.get(key), list):
                return value[key]
    raise ValueError("Kanban JSON did not contain a task list")


def identity(task):
    return str(task.get("id") or task.get("task_id") or json.dumps(task, sort_keys=True))

before = {identity(task) for task in tasks(sys.argv[1])}
new = [task for task in tasks(sys.argv[2]) if identity(task) not in before]
report = str(pathlib.Path(sys.argv[3]).resolve())
valid = [
    task for task in new
    if str(task.get("title", "")).startswith("intake: x ")
    and report in str(task.get("body", ""))
    and task.get("assignee") == "orchestrator"
    and task.get("created_by", task.get("createdBy")) == "triage-scout-x"
]
if len(valid) != 1:
    raise SystemExit(1)
PY
then
  echo "triage-scout-x: no matching new intake Kanban task was created" >&2
  exit 74
fi

if (( blocked_sweep == 1 )); then
  echo "triage-scout-x: blocked sweep report and escalation task created; X search did not complete" >&2
  exit 75
fi

echo "triage-scout-x: verified new intake report and Kanban task: $report_path"
