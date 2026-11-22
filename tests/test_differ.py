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
        "last_changed": "2026-11-01",
        "last_trend": None,
        "info_url": None,
        "info_checked": None,
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
    current = _snapshot(
        {"alpha": _entry(first_seen="2026-11-23", name="Alpha 2", last_changed="2026-11-23")}
    )
    assert diff_snapshots(previous, current).is_empty()


def test_change_direction_marks_better_and_worse() -> None:
    from opencode_monitor.differ import change_direction

    # Allowances: more is better, none is the floor, ∞ the ceiling.
    assert change_direction("go_allowance", "$60", "$120") == 1
    assert change_direction("go_allowance", "$500", "$200") == -1
    assert change_direction("go_allowance", None, "$60") == 1
    assert change_direction("go_allowance", "$60", None) == -1
    assert change_direction("go_plus_allowance", "$∞", "$500") == -1
    # Prices: cheaper is better.
    assert change_direction("input_cost_per_m", 2.0, 1.0) == 1
    assert change_direction("output_cost_per_m", 1.0, 2.0) == -1
    assert change_direction("input_cost_per_m", None, 1.0) == 0
    # Free tier and badges.
    assert change_direction("is_free", False, True) == 1
    assert change_direction("is_free", True, False) == -1
    assert change_direction("badges", ["New"], ["New", "Promo"]) == 1
    assert change_direction("badges", ["New", "Promo"], []) == -1
    assert change_direction("badges", ["New"], ["Promo"]) == 0


def test_trend_for_changes_aggregates() -> None:
    from opencode_monitor.differ import trend_for_changes
    from opencode_monitor.models import Change

    up = Change(key="a", field="go_allowance", old="$60", new="$120")
    down = Change(key="a", field="input_cost_per_m", old=1.0, new=2.0)
    neutral = Change(key="a", field="badges", old=["New"], new=["Promo"])
    assert trend_for_changes([up]) == "up"
    assert trend_for_changes([down]) == "down"
    assert trend_for_changes([neutral]) is None
    assert trend_for_changes([up, down]) is None  # mixed stays unmarked
