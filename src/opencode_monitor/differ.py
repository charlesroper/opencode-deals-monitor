"""Classifies added, changed, and removed items between two snapshots."""

from __future__ import annotations

from typing import Any

from .models import Change, DiffResult, Snapshot, allowance_value

# Only these fields trigger a "changed" event. Cosmetic reordering of badges
# never triggers a false diff.
TRACKED_FIELDS = (
    "go_allowance",
    "go_plus_allowance",
    "input_cost_per_m",
    "output_cost_per_m",
    "is_free",
    "badges",
)


def change_direction(field: str, old: Any, new: Any) -> int:
    """+1 when a change favours the reader, -1 when it goes against, 0 neutral."""
    if field in {"go_allowance", "go_plus_allowance"}:
        old_value = allowance_value(old)
        new_value = allowance_value(new)
        return 1 if new_value > old_value else -1 if new_value < old_value else 0
    if field in {"input_cost_per_m", "output_cost_per_m"}:
        if old is None or new is None:
            return 0
        return 1 if new < old else -1 if new > old else 0
    if field == "is_free":
        return 1 if new and not old else -1 if old and not new else 0
    if field == "badges":
        old_count = len(old) if isinstance(old, list) else 0
        new_count = len(new) if isinstance(new, list) else 0
        return 1 if new_count > old_count else -1 if new_count < old_count else 0
    return 0


def trend_for_changes(changes: list[Change]) -> str | None:
    """Overall direction for one model's changes: up, down, or mixed."""
    directions = {
        change_direction(change.field, change.old, change.new) for change in changes
    }
    positive = 1 in directions
    negative = -1 in directions
    if positive and not negative:
        return "up"
    if negative and not positive:
        return "down"
    return None


def _equivalent(old: object, new: object) -> bool:
    if isinstance(old, list) and isinstance(new, list):
        return sorted(old) == sorted(new)
    return old == new


def diff_snapshots(previous: Snapshot, current: Snapshot) -> DiffResult:
    """Compare the tracked fields of two snapshots."""
    old_models = previous["models"]
    new_models = current["models"]

    added = sorted(set(new_models) - set(old_models))
    removed = sorted(set(old_models) - set(new_models))

    changed: list[Change] = []
    for key in sorted(set(old_models) & set(new_models)):
        old_entry = old_models[key]
        new_entry = new_models[key]
        for field_name in TRACKED_FIELDS:
            old_value = old_entry[field_name]
            new_value = new_entry[field_name]
            if not _equivalent(old_value, new_value):
                changed.append(
                    Change(
                        key=key,
                        field=field_name,
                        old=old_value,
                        new=new_value,
                    )
                )

    return DiffResult(added=added, changed=changed, removed=removed)
