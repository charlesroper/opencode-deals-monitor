"""Classifies added, changed, and removed items between two snapshots."""

from __future__ import annotations

from .models import Change, DiffResult, Snapshot

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
