"""CLI entrypoint: fetch, merge, diff, and publish."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .atom_builder import build_feed, entry_id
from .config import Settings
from .console_html import parse_console_html
from .differ import diff_snapshots
from .fetcher import FetchError, fetch_text
from .html_builder import build_page
from .merger import merge_snapshot
from .models import ApiModel, ConsoleModel, DiffResult, HistoryEntry, ModelEntry, Snapshot
from .models_api import parse_models_api
from .state_store import load_json, write_json_atomic, write_text_atomic


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _diff_title(diff: DiffResult) -> str:
    parts: list[str] = []
    if diff.added:
        parts.append(_plural(len(diff.added), "model started"))
    if diff.changed:
        parts.append(_plural(len(diff.changed), "change"))
    if diff.removed:
        parts.append(_plural(len(diff.removed), "model ended"))
    return ", ".join(parts) or "No changes"


def _is_promo(entry: ModelEntry) -> bool:
    return bool(entry["badges"]) or entry["is_free"]


def _load_models_api(args: argparse.Namespace, settings: Settings) -> dict[str, ApiModel]:
    if args.json_fixture:
        text = Path(args.json_fixture).read_text(encoding="utf-8")
    else:
        text = fetch_text(settings.models_api_url)
    return parse_models_api(json.loads(text))


def _load_console_html(args: argparse.Namespace, settings: Settings) -> str | None:
    if args.html_fixture:
        return Path(args.html_fixture).read_text(encoding="utf-8")
    try:
        return fetch_text(settings.console_go_url)
    except FetchError as exc:
        print(f"warning: console scrape failed: {exc}", file=sys.stderr)
        return None


def _history_entry(
    snapshot: Snapshot, diff: DiffResult, timestamp: str, *, first_run: bool
) -> HistoryEntry:
    if first_run:
        promo_count = sum(1 for entry in snapshot["models"].values() if _is_promo(entry))
        return HistoryEntry(
            id=entry_id(timestamp, [], [], []),
            timestamp=timestamp,
            title=f"Monitoring started: {len(snapshot['models'])} models tracked",
            added=[],
            changed=[],
            removed=[],
            degraded=snapshot["console_html_degraded"],
            note=f"Baseline snapshot: {promo_count} models have an active promo or free tier.",
        )
    return HistoryEntry(
        id=entry_id(timestamp, diff.added, [asdict(c) for c in diff.changed], diff.removed),
        timestamp=timestamp,
        title=_diff_title(diff),
        added=list(diff.added),
        changed=[asdict(c) for c in diff.changed],
        removed=list(diff.removed),
        degraded=snapshot["console_html_degraded"],
        note="",
    )


def _step_summary_path() -> Path | None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    return Path(summary) if summary else None


def _append_step_summary(
    snapshot: Snapshot, diff: DiffResult, *, first_run: bool, settings: Settings
) -> None:
    path = _step_summary_path()
    if path is None:
        return
    degraded = snapshot["console_html_degraded"]
    if first_run:
        status = "initialised" + (" (degraded)" if degraded else "")
    elif degraded:
        status = "degraded update"
    else:
        status = "updated"
    lines = [
        f"## {settings.feed_title}",
        "",
        f"- Status: {status}",
        f"- Models tracked: {len(snapshot['models'])}",
        "- Console scrape: "
        + (
            f"degraded, allowances carried forward from {snapshot['console_html_verified_at']}"
            if degraded
            else f"healthy, verified {snapshot['console_html_verified_at']}"
        ),
    ]
    if not diff.is_empty():
        lines.append(f"- {_diff_title(diff)}")
        for label, items in (("Starting", diff.added), ("Ended", diff.removed)):
            if items:
                shown = ", ".join(items[:10]) + ("…" if len(items) > 10 else "")
                lines.append(f"- {label}: {shown}")
        if diff.changed:
            shown = ", ".join(f"{c.key} ({c.field})" for c in diff.changed[:10])
            lines.append(f"- Changed: {shown}" + ("…" if len(diff.changed) > 10 else ""))
    path.open("a", encoding="utf-8").write("\n".join(lines) + "\n")


def _print_diff(diff: DiffResult, snapshot: Snapshot, *, first_run: bool) -> None:
    if first_run:
        promo_count = sum(1 for entry in snapshot["models"].values() if _is_promo(entry))
        print(
            f"First run: would track {len(snapshot['models'])} models, "
            f"{promo_count} with an active promo or free tier."
        )
        return
    print(_diff_title(diff))
    for name in diff.added:
        print(f"  started: {name}")
    for change in diff.changed:
        print(f"  changed: {change.key}: {change.field} {change.old!r} -> {change.new!r}")
    for name in diff.removed:
        print(f"  ended: {name}")


def _to_snapshot(payload: Any) -> Snapshot | None:
    """Validate a loaded state.json payload before trusting it."""
    if payload is None:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), dict):
        msg = "data/state.json is not a valid snapshot"
        raise ValueError(msg)
    return payload  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opencode-monitor",
        description="Monitor OpenCode Go model deals and publish changes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the computed diff without writing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild public outputs even when no diff is detected",
    )
    parser.add_argument("--verbose", action="store_true", help="log quiet runs")
    parser.add_argument(
        "--json-fixture", metavar="PATH", help="read models.dev JSON from a local file"
    )
    parser.add_argument(
        "--html-fixture", metavar="PATH", help="read Console HTML from a local file"
    )
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. models.dev is the primary source: a failure here is fatal.
    try:
        api_models = _load_models_api(args, settings)
    except (FetchError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: models.dev fetch or parse failed: {exc}", file=sys.stderr)
        return 1
    if not api_models:
        print("error: models.dev payload contained no tracked models", file=sys.stderr)
        return 1

    # 2. Console HTML is degradable: a failure here means carried-forward
    #    allowances and a stale-data notice, never a false "deal ended".
    html_text = _load_console_html(args, settings)
    console_models: dict[str, ConsoleModel] = (
        parse_console_html(html_text) if html_text is not None else {}
    )
    if html_text is not None and not console_models:
        print(
            "warning: console HTML parsed 0 models; treating scrape as degraded",
            file=sys.stderr,
        )

    previous = _to_snapshot(load_json(settings.state_path))
    history: list[HistoryEntry] = load_json(settings.history_path) or []
    first_run = previous is None

    snapshot = merge_snapshot(
        api_models,
        console_models,
        previous,
        now=now,
        html_fetch_failed=html_text is None,
    )
    if snapshot["console_html_degraded"]:
        print(
            "warning: console scrape degraded; Go / Go Plus allowances carried "
            f"forward from {snapshot['console_html_verified_at']}",
            file=sys.stderr,
        )

    diff = DiffResult() if first_run else diff_snapshots(previous, snapshot)

    # A tracked-field change stamps the model's last_changed date.
    today = now.strftime("%Y-%m-%d")
    for change in diff.changed:
        changed_entry = snapshot["models"].get(change.key)
        if changed_entry is not None:
            changed_entry["last_changed"] = today

    # A run that flips the degradation flag must publish even with no diff:
    # the state file records the flag, and recovery must clear it on disk.
    degraded_flip = (
        previous is not None
        and previous["console_html_degraded"] != snapshot["console_html_degraded"]
    )
    quiet = (
        not first_run
        and diff.is_empty()
        and not snapshot["console_html_degraded"]
        and not degraded_flip
    )
    if quiet and not args.force:
        if args.dry_run:
            _print_diff(diff, snapshot, first_run=first_run)
        elif args.verbose:
            print("No changes; nothing written.")
        return 0

    if args.dry_run:
        _print_diff(diff, snapshot, first_run=first_run)
        return 2 if snapshot["console_html_degraded"] else 0

    # 3. Persist state and history when something actually changed. A pure
    #    --force rebuild touches only the public outputs.
    write_state = (
        first_run
        or not diff.is_empty()
        or snapshot["console_html_degraded"]
        or degraded_flip
    )
    if write_state:
        history_entry = _history_entry(snapshot, diff, timestamp, first_run=first_run)
        history = [*history, history_entry][-settings.history_limit :]
        write_json_atomic(settings.state_path, snapshot)
        write_json_atomic(settings.history_path, history)

    # 4. Publish the static outputs atomically.
    feed = build_feed(history, settings)
    page = build_page(snapshot, history, settings)
    write_text_atomic(settings.feed_path, feed)
    write_text_atomic(settings.html_path, page)
    write_json_atomic(settings.deals_path, snapshot)

    _append_step_summary(snapshot, diff, first_run=first_run, settings=settings)

    if first_run:
        promo_count = sum(1 for entry in snapshot["models"].values() if _is_promo(entry))
        print(
            f"Initialised: tracking {len(snapshot['models'])} models, "
            f"{promo_count} with an active promo or free tier."
        )
    elif diff.is_empty():
        print("Rebuilt public outputs; no model changes.")
    else:
        print(
            f"Updated {_diff_title(diff)}; "
            f"{len(snapshot['models'])} models tracked."
        )
    return 2 if snapshot["console_html_degraded"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
