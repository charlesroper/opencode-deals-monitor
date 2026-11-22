"""Differ tests: added, changed, removed, and quiet classification."""

from __future__ import annotations

from opencode_monitor.differ import diff_snapshots
from opencode_monitor.models import Snapshot


def _entry(**overrides) -> dict:
    base = {
        "key": "alpha",
        "id": "alpha",
        "name": "Alpha",
        "providers": ["opencode-go"],
        "context_limit": 1000,
        "output_limit": 100,
        "input_cost_per_m": 1.0,
        "output_cost_per_m": 2.0,
        "go_allowance": "$60",
        "go_plus_allowance": "$120",
        "badges": [],
        "is_free": False,
        "first_seen": "2026-11-01",
        "allowance_since": "2026-11-01",
    }
    base.update(overrides)
    return base


def _snapshot(models: dict) -> Snapshot:
    return Snapshot(
        updated_at="2026-11-23T08:23:00Z",
        console_html_verified_at="2026-11-23T08:23:00Z",
        console_html_degraded=False,
        models=models,
    )


def test_no_change_is_quiet() -> None:
    previous = _snapshot({"alpha": _entry()})
    current = _snapshot({"alpha": _entry()})
    assert diff_snapshots(previous, current).is_empty()


def test_added_and_removed() -> None:
    previous = _snapshot({"alpha": _entry()})
    current = _snapshot({"alpha": _entry(), "beta": _entry(key="beta", id="beta", name="Beta")})
    diff = diff_snapshots(previous, current)
    assert diff.added == ["beta"]
    assert diff.changed == []
    assert diff.removed == []

    diff = diff_snapshots(current, previous)
    assert diff.removed == ["beta"]


def test_allowance_change_recorded_with_old_and_new() -> None:
    previous = _snapshot({"alpha": _entry()})
    current = _snapshot({"alpha": _entry(go_allowance="$90")})
    diff = diff_snapshots(previous, current)
    assert len(diff.changed) == 1
    change = diff.changed[0]
    assert change.key == "alpha"
    assert change.field == "go_allowance"
    assert change.old == "$60"
    assert change.new == "$90"


def test_cost_isfree_and_badge_changes_tracked() -> None:
    previous = _snapshot({"alpha": _entry()})
    current = _snapshot(
        {
            "alpha": _entry(
                input_cost_per_m=0.5,
                output_cost_per_m=1.0,
                is_free=True,
                badges=["New"],
            )
        }
    )
    diff = diff_snapshots(previous, current)
    fields = {change.field for change in diff.changed}
    assert fields == {"input_cost_per_m", "output_cost_per_m", "is_free", "badges"}


def test_badge_reorder_is_not_a_change() -> None:
    previous = _snapshot({"alpha": _entry(badges=["New", "Promo"])})
    current = _snapshot({"alpha": _entry(badges=["Promo", "New"])})
    assert diff_snapshots(previous, current).is_empty()


def test_untracked_fields_ignored() -> None:
    previous = _snapshot({"alpha": _entry()})
    current = _snapshot({"alpha": _entry(first_seen="2026-11-23", name="Alpha 2")})
    assert diff_snapshots(previous, current).is_empty()
