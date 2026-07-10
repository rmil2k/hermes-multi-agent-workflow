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
    sub.add_parser("scaffold", help="Print the setup plan from triage.yaml.").set_defaults(func=cmd_scaffold)
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
    sub.add_parser("init", help="(stub) Start a new project.").set_defaults(func=cmd_stub("init"))
    sub.add_parser("install", help="(stub) Execute the scaffold plan.").set_defaults(func=cmd_stub("install"))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
