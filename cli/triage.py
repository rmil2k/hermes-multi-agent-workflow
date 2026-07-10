#!/usr/bin/env python3
"""Triage engine CLI:  python -m cli.triage <command>

Commands:
  validate   Load triage.yaml and check it for consistency. FULLY IMPLEMENTED —
             run this after every edit.
  scaffold   Print the Hermes commands to create the profiles, install the skill
             templates, create the board, and register the scout crons implied by
             triage.yaml. PRINTS the plan; it does not execute (so you can review
             before running, and because the exact `hermes` invocations depend on
             your install). Marked TODO where you must confirm syntax.
  init       Stub. Intended to copy triage.yaml + path templates into a fresh
             project. For now, copy this repo and edit triage.yaml directly.
  install    Stub. Intended to actually run the scaffold plan. Left manual on
             purpose — review the printed commands and run them yourself.

This is a TEMPLATE. `scaffold`/`init`/`install` are intentionally conservative —
they tell you what to do rather than mutate your Hermes install behind your back.
Wire them up to your environment as you adopt the template.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable

from engine.config import ConfigError, TriageConfig

Runner = Callable[..., subprocess.CompletedProcess[str]]


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        cfg = TriageConfig.load(args.config)
    except ConfigError as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(f"[OK] triage.yaml valid - pipeline {cfg.name!r}")
    print(f"  board: {cfg.board}   workspace_root: {cfg.workspace_root}   cost_gate: ${cfg.cost_gate_usd}")
    print(f"  sources: {[s.id for s in cfg.sources]}")
    print(f"  rubric: {len(cfg.rubric.dimensions)} dims, threshold {cfg.rubric.threshold}/{cfg.rubric.max_total}")
    print(f"  research lanes: {cfg.research.lanes} (classifier: {cfg.research.classifier_lane})")
    print(f"  routes: {cfg.route.map}")
    print(f"  paths: {sorted(cfg.paths)}")
    print(f"  roles -> profiles: {cfg.roles}")
    # Warn about referenced-but-missing template files (non-fatal).
    missing = []
    for p in cfg.paths.values():
        for rel in (p.scope_rails, p.deliverable_spec, p.proposal_template):
            if rel and not cfg.resolve_path(rel).exists():
                missing.append(rel)
    if missing:
        print("  ! referenced template files not found (relative to triage.yaml; fill them in):")
        for m in sorted(set(missing)):
            print(f"      - {m}")
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    cfg = TriageConfig.load(args.config)
    print(f"# Scaffold plan for pipeline {cfg.name!r}. Review, then run the commands you trust.\n")
    print(f"# 1. Create the dedicated board")
    print(f"hermes kanban boards create {cfg.board}    # TODO: confirm subcommand on your Hermes version\n")
    print(f"# 2. Create the profiles (one per role + one per source profile)")
    profiles = sorted(set(cfg.roles.values()) | {s.profile for s in cfg.sources})
    for prof in profiles:
        print(f"hermes profile create {prof} --from <base-profile>   # TODO: set model in {prof}/config.yaml")
    print()
    print(f"# 3. Source profiles need the `kanban` toolset (they run via cron, not the dispatcher)")
    for s in cfg.sources:
        print(f"#   edit ~/.hermes/profiles/{s.profile}/config.yaml → toolsets: [hermes-cli, kanban]")
    print()
    print(f"# 4. Install skills: copy skills/templates/triage-orchestrator → orchestrator profile,")
    print(f"#    and triage-scout → each source profile (rename per source).")
    for s in cfg.sources:
        print(f"#   {s.skill} → profile {s.profile}")
    print()
    print(f"# 5. Register scout crons in the GATEWAY profile's store (v0.15.0+ reads only that store)")
    for s in cfg.sources:
        print(f"orchestrator cron create '{s.schedule}' --profile {s.profile} --skill {s.skill}   # TODO confirm flags")
    print()
    print(f"# 6. Start the runtime (WSL: foreground):  orchestrator gateway run")
    print(f"# See docs/07-runbook.md for the full go-live sequence.")
    return 0


def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, **kwargs)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def names_from_lines(output: str) -> set[str]:
    names: set[str] = set()
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        names.add(stripped.split()[0])
    return names


def local_template_warnings(cfg: TriageConfig) -> list[str]:
    missing: list[str] = []
    for path_def in cfg.paths.values():
        for rel in (path_def.scope_rails, path_def.deliverable_spec, path_def.proposal_template):
            if rel and not cfg.resolve_path(rel).exists():
                missing.append(rel)
    return sorted(set(missing))


def cmd_doctor(config_path: str | Path = "triage.yaml", *, runner: Runner = run_command) -> int:
    """Check whether the local Hermes environment looks ready for this pipeline."""
    failures = 0
    warnings = 0

    try:
        cfg = TriageConfig.load(config_path)
        print(f"[OK] triage.yaml - pipeline {cfg.name!r} is valid")
    except ConfigError as exc:
        print(f"[FAIL] triage.yaml - {exc}")
        return 1

    missing_templates = local_template_warnings(cfg)
    if missing_templates:
        warnings += 1
        print("[WARN] templates - referenced files missing relative to triage.yaml:")
        for rel in missing_templates:
            print(f"       - {rel}")
    else:
        print("[OK] templates - all referenced local files exist")

    hermes = runner(["hermes", "--version"])
    if hermes.returncode != 0:
        failures += 1
        detail = (hermes.stderr or hermes.stdout or "command failed").strip()
        print(f"[FAIL] Hermes CLI - cannot run `hermes --version`: {detail}")
        print(f"\nSummary: {failures} failure(s), {warnings} warning(s)")
        return 1
    version = (hermes.stdout or hermes.stderr).strip().splitlines()[0]
    print(f"[OK] Hermes CLI - {version}")

    board_result = runner(["hermes", "kanban", "boards", "list"])
    if board_result.returncode != 0:
        failures += 1
        detail = (board_result.stderr or board_result.stdout or "command failed").strip()
        print(f"[FAIL] board - could not list boards: {detail}")
    else:
        boards = names_from_lines(board_result.stdout)
        if cfg.board in boards:
            print(f"[OK] board - {cfg.board!r} exists")
        else:
            failures += 1
            print(f"[FAIL] board - {cfg.board!r} not found; create it with `hermes kanban boards create {cfg.board}`")

    profile_result = runner(["hermes", "profile", "list"])
    required_profiles = sorted(set(cfg.roles.values()) | {s.profile for s in cfg.sources})
    if profile_result.returncode != 0:
        failures += 1
        detail = (profile_result.stderr or profile_result.stdout or "command failed").strip()
        print(f"[FAIL] profiles - could not list profiles: {detail}")
    else:
        profiles = names_from_lines(profile_result.stdout)
        missing = [p for p in required_profiles if p not in profiles]
        if missing:
            failures += 1
            print("[FAIL] profiles - missing required Hermes profiles:")
            for prof in missing:
                print(f"       - {prof}")
        else:
            print(f"[OK] profiles - all {len(required_profiles)} required profiles exist")

    if cfg.sources:
        print("[INFO] scout profiles must include the `kanban` toolset:")
        for source in cfg.sources:
            print(f"       - {source.profile} for source {source.id!r}")

    print(f"\nSummary: {failures} failure(s), {warnings} warning(s)")
    return 1 if failures else 0


def cmd_doctor_from_args(args: argparse.Namespace) -> int:
    return cmd_doctor(args.config)


def cmd_stub(name: str):
    def run(args: argparse.Namespace) -> int:
        print(f"`{name}` is a stub in this template. See `python -m cli.triage scaffold` for the plan, "
              f"and docs/04-adapting-to-your-domain.md / docs/07-runbook.md. Wire it to your environment.")
        return 0
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cli.triage", description="Hermes Multi-Agent Workflow CLI.")
    parser.add_argument("--config", default="triage.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Validate triage.yaml.").set_defaults(func=cmd_validate)
    sub.add_parser("scaffold", help="Print the setup plan from triage.yaml.").set_defaults(func=cmd_scaffold)
    sub.add_parser("doctor", help="Check local Hermes readiness for this pipeline.").set_defaults(func=cmd_doctor_from_args)
    sub.add_parser("init", help="(stub) Start a new project.").set_defaults(func=cmd_stub("init"))
    sub.add_parser("install", help="(stub) Execute the scaffold plan.").set_defaults(func=cmd_stub("install"))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
