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
import os
import shutil
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable

from engine.config import ConfigError, TriageConfig
from engine.engine import TriageEngine
from engine.item_vault import ItemVault

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


def scaffold_commands(cfg: TriageConfig, *, base_profile: str = "default", paused: bool = True) -> list[list[str]]:
    """Build the Hermes CLI commands needed to scaffold this pipeline."""
    commands: list[list[str]] = [["hermes", "kanban", "boards", "create", cfg.board]]
    profiles = sorted(set(cfg.roles.values()) | {s.profile for s in cfg.sources})
    commands.extend(["hermes", "profile", "create", prof, "--clone-from", base_profile] for prof in profiles)
    commands.append([
        "hermes",
        "--profile",
        cfg.roles.get("orchestrator", "orchestrator"),
        "skills",
        "install",
        "skills/templates/triage-orchestrator/SKILL.md",
        "--name",
        "triage-orchestrator",
    ])
    for source in cfg.sources:
        commands.append([
            "hermes",
            "--profile",
            source.profile,
            "skills",
            "install",
            f"skills/templates/{source.skill}/SKILL.md",
            "--name",
            source.skill,
        ])
    for source in cfg.sources:
        commands.append(["hermes", "cron", "create", source.schedule, "--profile", source.profile, "--skill", source.skill])
    if paused:
        commands.append(["hermes", "cron", "pause", "all"])
    return commands


def shell_join(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def cmd_scaffold(args: argparse.Namespace) -> int:
    return cmd_scaffold_plan(
        args.config,
        base_profile=args.base_profile,
        apply=args.apply,
        paused=args.paused,
        skip_existing=args.skip_existing,
    )


def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, **kwargs)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def filter_existing_scaffold_commands(
    commands: list[list[str]],
    *,
    runner: Runner,
) -> list[list[str]]:
    board_result = runner(["hermes", "kanban", "boards", "list"])
    existing_boards = names_from_lines(board_result.stdout) if board_result.returncode == 0 else set()
    profile_result = runner(["hermes", "profile", "list"])
    existing_profiles = names_from_lines(profile_result.stdout) if profile_result.returncode == 0 else set()

    filtered: list[list[str]] = []
    for cmd in commands:
        if cmd[:4] == ["hermes", "kanban", "boards", "create"] and cmd[4] in existing_boards:
            print(f"[SKIP] Skipping existing board {cmd[4]!r}")
            continue
        if cmd[:3] == ["hermes", "profile", "create"] and cmd[3] in existing_profiles:
            print(f"[SKIP] Skipping existing profile {cmd[3]!r}")
            continue
        filtered.append(cmd)
    return filtered


def cmd_scaffold_plan(
    config_path: str | Path = "triage.yaml",
    *,
    base_profile: str = "default",
    apply: bool = False,
    paused: bool = True,
    skip_existing: bool = False,
    runner: Runner = run_command,
) -> int:
    try:
        cfg = TriageConfig.load(config_path)
    except ConfigError as exc:
        print(f"[FAIL] scaffold - {exc}")
        return 1

    commands = scaffold_commands(cfg, base_profile=base_profile, paused=paused)
    mode = "Apply" if apply else "Dry run"
    print(f"# {mode} scaffold plan for pipeline {cfg.name!r}")
    print(f"# Board: {cfg.board}")
    print("# Source profiles must include the `kanban` toolset before scouts go live.")
    print()
    if skip_existing:
        commands = filter_existing_scaffold_commands(commands, runner=runner)

    if not apply:
        for cmd in commands:
            print(shell_join(cmd))
        return 0

    for cmd in commands:
        print(f"$ {shell_join(cmd)}")
        result = runner(cmd)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "command failed").strip()
            print(f"[FAIL] command exited {result.returncode}: {detail}")
            return result.returncode or 1
    print(f"Applied {len(commands)} scaffold command(s).")
    return 0


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


def smoke_candidate() -> dict:
    return {
        "slug": "smoke-agent-workflow-pain",
        "title": "Agent users lose hours when workflows break silently",
        "claim": "Users report broken agent workflows, wasted hours, and blocked work.",
        "sources": [
            {"url": "https://example.com/source-1", "title": "Smoke source 1"},
            {"url": "https://example.com/source-2", "title": "Smoke source 2"},
            {"url": "https://example.com/source-3", "title": "Smoke source 3"},
            {"url": "https://example.com/source-4", "title": "Smoke source 4"},
        ],
        "why_it_may_matter": "Concrete pain: wasted hours, gave up, blocked teams.",
        "agent_solvable_or_explainable": "yes",
        "solution_gap": "missing",
        "strategic_fit": "agent",
    }


def first_non_auto_route_value(cfg: TriageConfig) -> tuple[str, str]:
    for classification, path_name in cfg.route.map.items():
        if not cfg.get_path(path_name).auto:
            return classification, path_name
    classification, path_name = next(iter(cfg.route.map.items()))
    return classification, path_name


def vault_for_config(cfg: TriageConfig, *, smoke: bool = False) -> ItemVault:
    root = cfg.resolve_path(cfg.workspace_root)
    if smoke:
        root = root / "smoke"
    return ItemVault(root / "vault" / "items")


def cmd_item_list(config_path: str | Path = "triage.yaml", *, smoke: bool = False) -> int:
    try:
        cfg = TriageConfig.load(config_path)
    except ConfigError as exc:
        print(f"[FAIL] config - {exc}")
        return 1
    vault = vault_for_config(cfg, smoke=smoke)
    label = "smoke" if smoke else "live"
    print(f"# {label} item vault: {vault.root}")
    print("slug\tstatus\tpath\tscore\ttitle")
    for path in sorted(vault.root.glob("*.md")):
        item = vault.load(path.stem)
        fm = item.frontmatter
        print(f"{fm.get('slug', path.stem)}\t{fm.get('status', '')}\t{fm.get('path', '')}\t{fm.get('score', '')}\t{fm.get('title', '')}")
    return 0


def cmd_item_show(config_path: str | Path, slug: str, *, smoke: bool = False) -> int:
    try:
        cfg = TriageConfig.load(config_path)
        vault = vault_for_config(cfg, smoke=smoke)
        item = vault.load(slug)
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"[FAIL] item - {exc}")
        return 1
    fm = item.frontmatter
    print(f"# {fm.get('title', slug)}")
    print(f"slug: {fm.get('slug', slug)}")
    print(f"status: {fm.get('status', '')}")
    print(f"path: {fm.get('path', '')}")
    print(f"score: {fm.get('score', '')}")
    print("\n## Events")
    for event in fm.get("events", []):
        extras = " ".join(f"{k}={v}" for k, v in event.items() if k not in {"at", "event"})
        print(f"- {event.get('at', '')} {event.get('event', '')} {extras}".rstrip())
    print("\n## Body\n")
    print(item.body.strip())
    return 0


def cmd_item_from_args(args: argparse.Namespace) -> int:
    if args.item_command == "list":
        return cmd_item_list(args.config, smoke=args.smoke)
    if args.item_command == "show":
        return cmd_item_show(args.config, args.slug, smoke=args.smoke)
    print("[FAIL] item - expected subcommand: list or show")
    return 1


def hermes_bin() -> str:
    return os.environ.get("HERMES_BIN") or shutil.which("hermes") or "/opt/hermes/bin/hermes"


def gate_send_command(cfg: TriageConfig, proposal_file: Path, *, subject: str | None = None) -> list[str]:
    """Build the exact Hermes CLI command that notifies the human gate.

    `gate.target` may be a full Hermes send target such as `discord:<dm_id>`.
    If omitted, `gate.channel` is used, which sends to that platform's configured
    home channel/DM.
    """
    hermes = hermes_bin()
    target = cfg.gate.target or cfg.gate.channel
    cmd = [hermes, "send", "--to", target]
    if subject:
        cmd.extend(["--subject", subject])
    cmd.extend(["--file", str(proposal_file)])
    return cmd


def cmd_gate_notify(
    config_path: str | Path,
    proposal_file: str | Path,
    *,
    subject: str | None = None,
    apply: bool = False,
    runner: Runner = run_command,
) -> int:
    try:
        cfg = TriageConfig.load(config_path)
    except ConfigError as exc:
        print(f"[FAIL] gate notify - {exc}")
        return 1
    proposal_path = Path(proposal_file)
    if not proposal_path.exists():
        print(f"[FAIL] gate notify - proposal file not found: {proposal_path}")
        return 1
    cmd = gate_send_command(cfg, proposal_path, subject=subject)
    if not apply:
        print(shell_join(cmd))
        return 0
    result = runner(cmd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        print(f"[FAIL] gate notify - command exited {result.returncode}: {detail}")
        return result.returncode or 1
    if result.stdout.strip():
        print(result.stdout.strip())
    print(f"[OK] gate notify - sent proposal to {cfg.gate.target or cfg.gate.channel}")
    return 0


def cmd_gate_from_args(args: argparse.Namespace) -> int:
    if args.gate_command == "notify":
        return cmd_gate_notify(
            args.config,
            args.file,
            subject=args.subject,
            apply=args.apply,
        )
    print("[FAIL] gate - expected subcommand: notify")
    return 1


def cmd_smoke_test(config_path: str | Path = "triage.yaml") -> int:
    """Run a no-network, no-live-Hermes simulation of one item lifecycle."""
    try:
        cfg = TriageConfig.load(config_path)
    except ConfigError as exc:
        print(f"[FAIL] config - {exc}")
        return 1

    vault = vault_for_config(cfg, smoke=True)
    engine = TriageEngine(cfg, vault)
    candidate = smoke_candidate()
    slug = candidate["slug"]
    candidate_text = f"{candidate['title']}\n{candidate['claim']}\n{candidate['why_it_may_matter']}"

    existing = vault.item_path(slug)
    if existing.exists():
        existing.unlink()

    print(f"[OK] config - loaded pipeline {cfg.name!r}")

    matches = engine.dedup(candidate_text)
    blocking = [m for m in matches if m.decision == "duplicate"]
    if blocking:
        print(f"[FAIL] dedup - candidate matched duplicate {blocking[0].slug!r}")
        return 1
    print(f"[OK] dedup - no duplicate found ({len(matches)} prior match(es) checked)")

    score = engine.score_heuristic(candidate)
    if not score.advance:
        print(f"[FAIL] score - smoke candidate scored {score.total}/{cfg.rubric.max_total}, below threshold {cfg.rubric.threshold}")
        return 1
    print(f"[OK] score - {score.total}/{cfg.rubric.max_total} clears threshold {cfg.rubric.threshold}")

    item = vault.create_item(
        slug=slug,
        title=candidate["title"],
        sources=candidate["sources"],
        body=candidate_text,
    )
    vault.append_event(slug, "created", source="smoke-test")
    vault.append_event(slug, "dedup_checked", matches=len(matches))
    item = vault.load(slug)
    item.frontmatter["score"] = score.total
    item.frontmatter["score_breakdown"] = score.breakdown
    item.frontmatter["status"] = "researching"
    vault.save(item)
    vault.append_event(slug, "scored", score=score.total, advance=score.advance)

    research = engine.research_specs(slug, "smoke-triage-task")
    if len(research) != len(cfg.research.lanes):
        print(f"[FAIL] research - expected {len(cfg.research.lanes)} specs, got {len(research)}")
        return 1
    print(f"[OK] research - built {len(research)} parallel lane spec(s)")
    vault.append_event(slug, "research_specs_built", lanes=len(research))

    classification, expected_path = first_non_auto_route_value(cfg)
    routed_path = engine.route(classification)
    if routed_path != expected_path:
        print(f"[FAIL] route - {classification!r} routed to {routed_path!r}, expected {expected_path!r}")
        return 1
    print(f"[OK] route - classifier value {classification!r} maps to path {routed_path!r}")
    vault.append_event(slug, "routed", classification=classification, path=routed_path)

    prep = engine.prep_specs(slug, routed_path)
    if not cfg.get_path(routed_path).auto and not prep:
        print(f"[FAIL] prep - path {routed_path!r} produced no prep specs")
        return 1
    print(f"[OK] prep - built {len(prep)} pre-gate task spec(s)")
    vault.append_event(slug, "prep_specs_built", tasks=len(prep))

    item = vault.load(slug)
    item.frontmatter["path"] = routed_path
    item.frontmatter["status"] = "awaiting_approval"
    item.frontmatter["linked_kanban_tasks"] = ["smoke-triage-task"]
    vault.save(item)
    vault.append_event(slug, "awaiting_approval")
    print("[OK] approval - simulated human gate at awaiting_approval")

    fulfillment = engine.fulfillment_specs(slug, routed_path)
    if not cfg.get_path(routed_path).auto and not fulfillment:
        print(f"[FAIL] fulfillment - path {routed_path!r} produced no fulfillment specs")
        return 1
    for spec in fulfillment:
        if spec.workspace_kind != "dir" or not spec.workspace_path:
            print(f"[FAIL] fulfillment - {spec.title!r} did not use a persistent dir workspace")
            return 1
    item = vault.load(slug)
    item.frontmatter["status"] = "approved"
    vault.save(item)
    vault.append_event(slug, "approved", fulfillment_tasks=len(fulfillment))
    print(f"[OK] fulfillment - built {len(fulfillment)} persistent post-gate task spec(s)")

    item = vault.load(slug)
    print(f"\nSmoke test passed. Item written to: {item.path}")
    return 0


def cmd_smoke_test_from_args(args: argparse.Namespace) -> int:
    return cmd_smoke_test(args.config)


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
    scaffold = sub.add_parser("scaffold", help="Print or apply the setup plan from triage.yaml.")
    scaffold.add_argument("--base-profile", default="default", help="Profile to clone when creating role/source profiles.")
    scaffold.add_argument("--apply", action="store_true", help="Execute the scaffold commands instead of printing them.")
    scaffold.add_argument("--skip-existing", action="store_true", help="Skip board/profile create commands when they already exist.")
    scaffold.add_argument("--no-paused", dest="paused", action="store_false", help="Do not append a cron pause command to the plan.")
    scaffold.set_defaults(func=cmd_scaffold, paused=True)
    sub.add_parser("doctor", help="Check local Hermes readiness for this pipeline.").set_defaults(func=cmd_doctor_from_args)
    sub.add_parser("smoke-test", help="Simulate one item lifecycle locally without live Hermes agents.").set_defaults(func=cmd_smoke_test_from_args)
    item = sub.add_parser("item", help="Inspect local item vault records.")
    item_sub = item.add_subparsers(dest="item_command", required=True)
    item_list = item_sub.add_parser("list", help="List item records from the live vault by default.")
    item_list.add_argument("--smoke", action="store_true", help="Read from the smoke-test vault instead of the live vault.")
    item_show = item_sub.add_parser("show", help="Show one item record from the live vault by default.")
    item_show.add_argument("slug")
    item_show.add_argument("--smoke", action="store_true", help="Read from the smoke-test vault instead of the live vault.")
    item.set_defaults(func=cmd_item_from_args)
    gate = sub.add_parser("gate", help="Human-gate notification helpers.")
    gate_sub = gate.add_subparsers(dest="gate_command", required=True)
    gate_notify = gate_sub.add_parser("notify", help="Send or print the configured human-gate proposal notification.")
    gate_notify.add_argument("--file", required=True, help="Markdown proposal file to send.")
    gate_notify.add_argument("--subject", default=None, help="Optional subject/header line.")
    gate_notify.add_argument("--apply", action="store_true", help="Actually run hermes send. Default is dry-run print.")
    gate.set_defaults(func=cmd_gate_from_args)
    sub.add_parser("init", help="(stub) Start a new project.").set_defaults(func=cmd_stub("init"))
    sub.add_parser("install", help="(stub) Execute the scaffold plan.").set_defaults(func=cmd_stub("install"))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
