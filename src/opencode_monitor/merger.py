"""Merges models.dev and Console HTML data into a snapshot."""

from __future__ import annotations

from datetime import UTC, datetime

from .models import (
    ApiModel,
    ConsoleModel,
    ModelEntry,
    Snapshot,
)

_DEGRADATION_DROP_RATIO = 0.5


def _date(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%d")


def _iso(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_console_degraded(
    console_models: dict[str, ConsoleModel],
    previous: Snapshot | None,
    html_fetch_failed: bool,
) -> bool:
    """True when the Console scrape failed, parsed nothing, or dropped >50%."""
    if html_fetch_failed or not console_models:
        return True
    if previous is None:
        return False
    previous_count = sum(
        1 for entry in previous["models"].values() if entry["go_allowance"] is not None
    )
    return previous_count > 0 and len(console_models) < previous_count * _DEGRADATION_DROP_RATIO


def _console_fields(entry: ModelEntry, console: ConsoleModel, today: str) -> None:
    entry["go_allowance"] = console.go_allowance
    entry["go_plus_allowance"] = console.go_plus_allowance
    entry["badges"] = list(console.badges)
    entry["allowance_since"] = today
    entry["is_free"] = entry["is_free"] or console.is_free


def _carry_forward(entry: ModelEntry, previous_entry: ModelEntry | None) -> None:
    """On a degraded scrape, keep the previous Console-derived fields."""
    if previous_entry is None:
        return
    entry["go_allowance"] = previous_entry["go_allowance"]
    entry["go_plus_allowance"] = previous_entry["go_plus_allowance"]
    entry["badges"] = previous_entry["badges"]
    entry["allowance_since"] = previous_entry["allowance_since"]
    # is_free stays models.dev-derived: masking a real free-tier change on a
    # degraded day would hide a genuine deal signal.


def _backfill_last_changed(previous_entry: ModelEntry | None) -> str | None:
    """Best-known change date for models tracked before last_changed existed."""
    if previous_entry is None:
        return None
    explicit = previous_entry.get("last_changed")
    if explicit:
        return explicit
    candidates = [previous_entry["first_seen"]]
    allowance_since = previous_entry.get("allowance_since")
    if allowance_since:
        candidates.append(allowance_since)
    return max(candidates)


def merge_snapshot(
    api_models: dict[str, ApiModel],
    console_models: dict[str, ConsoleModel],
    previous: Snapshot | None,
    *,
    now: datetime,
    html_fetch_failed: bool = False,
) -> Snapshot:
    """Build the merged snapshot.

    Console rows join onto models.dev entries by normalised key. Unmatched
    entries from either source are retained. When the Console scrape is
    degraded, previous allowances, badges, and the verified-at timestamp are
    carried forward so no false "deal ended" diffs are emitted.
    """
    today = _date(now)
    degraded = is_console_degraded(console_models, previous, html_fetch_failed)
    previous_models = previous["models"] if previous else {}

    entries: dict[str, ModelEntry] = {}

    for key, api in api_models.items():
        previous_entry = previous_models.get(key)
        entry = ModelEntry(
            key=key,
            id=api.id,
            name=api.name,
            providers=list(api.providers),
            context_limit=api.context_limit,
            output_limit=api.output_limit,
            input_cost_per_m=api.input_cost_per_m,
            output_cost_per_m=api.output_cost_per_m,
            go_allowance=None,
            go_plus_allowance=None,
            badges=[],
            is_free=api.is_free,
            first_seen=previous_entry["first_seen"] if previous_entry else today,
            allowance_since=None,
            last_changed=_backfill_last_changed(previous_entry) or today,
            last_trend=previous_entry.get("last_trend") if previous_entry else None,
            info_url=previous_entry.get("info_url") if previous_entry else None,
            info_checked=previous_entry.get("info_checked") if previous_entry else None,
        )
        console = console_models.get(key)
        if console is not None:
            _console_fields(entry, console, today)
        elif degraded:
            _carry_forward(entry, previous_entry)
        entries[key] = entry

    for key, console in console_models.items():
        if key in entries:
            continue
        previous_entry = previous_models.get(key)
        entry = ModelEntry(
            key=key,
            id=console.name,
            name=console.name,
            providers=[],
            context_limit=None,
            output_limit=None,
            input_cost_per_m=None,
            output_cost_per_m=None,
            go_allowance=console.go_allowance,
            go_plus_allowance=console.go_plus_allowance,
            badges=list(console.badges),
            is_free=console.is_free,
            first_seen=previous_entry["first_seen"] if previous_entry else today,
            allowance_since=today,
            last_changed=_backfill_last_changed(previous_entry) or today,
            last_trend=previous_entry.get("last_trend") if previous_entry else None,
            info_url=previous_entry.get("info_url") if previous_entry else None,
            info_checked=previous_entry.get("info_checked") if previous_entry else None,
        )
        entries[key] = entry

    # allowance_since only resets when the allowance value actually changed.
    if previous is not None and not degraded:
        for key, entry in entries.items():
            previous_entry = previous_models.get(key)
            if previous_entry is None:
                continue
            if (
                entry["go_allowance"] == previous_entry["go_allowance"]
                and entry["go_plus_allowance"] == previous_entry["go_plus_allowance"]
                and entry["allowance_since"] is not None
            ):
                entry["allowance_since"] = previous_entry["allowance_since"]

    verified_at: str | None
    if degraded:
        verified_at = previous["console_html_verified_at"] if previous else None
    else:
        verified_at = _iso(now)

    return Snapshot(
        updated_at=_iso(now),
        console_html_verified_at=verified_at,
        console_html_degraded=degraded,
        models=dict(sorted(entries.items())),
    )
