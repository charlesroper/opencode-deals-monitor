"""Merger tests: joining, retention, first_seen, degradation, recovery."""

from __future__ import annotations

from datetime import UTC, datetime

from opencode_monitor.merger import is_console_degraded, merge_snapshot
from opencode_monitor.models import ApiModel, ConsoleModel, Snapshot

NOW = datetime(2026, 11, 23, 8, 23, tzinfo=UTC)
TODAY = "2026-11-23"


def _api(key: str, *, is_free: bool = False) -> ApiModel:
    return ApiModel(
        key=key,
        id=key,
        name=key.upper(),
        providers=("opencode-go",),
        context_limit=1000,
        output_limit=100,
        input_cost_per_m=1.0,
        output_cost_per_m=2.0,
        is_free=is_free,
    )


def _console(
    key: str, go: str = "$60", go_plus: str = "$120", badges: tuple[str, ...] = ()
) -> ConsoleModel:
    return ConsoleModel(
        key=key,
        name=key.upper(),
        go_allowance=go,
        go_plus_allowance=go_plus,
        badges=badges,
        is_free=False,
    )


def _snapshot(models: dict, *, verified_at: str | None = "2026-11-22T08:23:00Z") -> Snapshot:
    return Snapshot(
        updated_at="2026-11-22T08:23:00Z",
        console_html_verified_at=verified_at,
        console_html_degraded=False,
        models=models,
    )


def test_join_by_normalised_key() -> None:
    console = _console("glm53", "$500", "$1,000")
    snapshot = merge_snapshot({"glm53": _api("glm53")}, {"glm53": console}, None, now=NOW)
    entry = snapshot["models"]["glm53"]
    assert entry["go_allowance"] == "$500"
    assert entry["go_plus_allowance"] == "$1,000"
    assert entry["first_seen"] == TODAY
    assert entry["allowance_since"] == TODAY


def test_unmatched_entries_retained() -> None:
    snapshot = merge_snapshot(
        {"alpha": _api("alpha")},
        {"beta": _console("beta")},
        None,
        now=NOW,
    )
    assert "alpha" in snapshot["models"]
    beta = snapshot["models"]["beta"]
    assert beta["go_allowance"] == "$60"
    assert beta["providers"] == []
    assert beta["first_seen"] == TODAY


def test_first_seen_preserved_and_allowance_since_resets() -> None:
    previous = _snapshot(
        {
            "alpha": {
                "key": "alpha",
                "id": "alpha",
                "name": "ALPHA",
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
                "allowance_since": "2026-11-02",
            }
        }
    )
    # Same allowance: first_seen and allowance_since carry over.
    snapshot = merge_snapshot(
        {"alpha": _api("alpha")}, {"alpha": _console("alpha")}, previous, now=NOW
    )
    entry = snapshot["models"]["alpha"]
    assert entry["first_seen"] == "2026-11-01"
    assert entry["allowance_since"] == "2026-11-02"

    # Allowance changed: allowance_since resets to today.
    snapshot = merge_snapshot(
        {"alpha": _api("alpha")}, {"alpha": _console("alpha", "$90")}, previous, now=NOW
    )
    assert snapshot["models"]["alpha"]["allowance_since"] == TODAY


def test_degraded_scrape_carries_fields_forward() -> None:
    previous = _snapshot(
        {
            "alpha": {
                "key": "alpha",
                "id": "alpha",
                "name": "ALPHA",
                "providers": ["opencode-go"],
                "context_limit": 1000,
                "output_limit": 100,
                "input_cost_per_m": 1.0,
                "output_cost_per_m": 2.0,
                "go_allowance": "$60",
                "go_plus_allowance": "$120",
                "badges": ["Promo"],
                "is_free": False,
                "first_seen": "2026-11-01",
                "allowance_since": "2026-11-02",
            }
        }
    )
    snapshot = merge_snapshot(
        {"alpha": _api("alpha")}, {}, previous, now=NOW, html_fetch_failed=True
    )
    entry = snapshot["models"]["alpha"]
    assert snapshot["console_html_degraded"] is True
    assert snapshot["console_html_verified_at"] == "2026-11-22T08:23:00Z"
    assert entry["go_allowance"] == "$60"
    assert entry["go_plus_allowance"] == "$120"
    assert entry["badges"] == ["Promo"]
    assert entry["allowance_since"] == "2026-11-02"


def test_recovery_clears_degraded_flag() -> None:
    previous = _snapshot(
        {
            "alpha": {
                "key": "alpha",
                "id": "alpha",
                "name": "ALPHA",
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
                "allowance_since": "2026-11-02",
            }
        }
    )
    previous["console_html_degraded"] = True
    snapshot = merge_snapshot(
        {"alpha": _api("alpha")}, {"alpha": _console("alpha")}, previous, now=NOW
    )
    assert snapshot["console_html_degraded"] is False
    assert snapshot["console_html_verified_at"] == "2026-11-23T08:23:00Z"


def test_drop_over_half_is_degraded() -> None:
    previous_models = {
        f"m{i}": {
            "key": f"m{i}",
            "id": f"m{i}",
            "name": f"M{i}",
            "providers": [],
            "context_limit": None,
            "output_limit": None,
            "input_cost_per_m": None,
            "output_cost_per_m": None,
            "go_allowance": "$60",
            "go_plus_allowance": "$120",
            "badges": [],
            "is_free": False,
            "first_seen": "2026-11-01",
            "allowance_since": "2026-11-01",
        }
        for i in range(10)
    }
    previous = _snapshot(previous_models)
    surviving = {f"m{i}": _console(f"m{i}") for i in range(4)}
    assert is_console_degraded(surviving, previous, html_fetch_failed=False) is True
    healthy = {f"m{i}": _console(f"m{i}") for i in range(6)}
    assert is_console_degraded(healthy, previous, html_fetch_failed=False) is False


def test_models_sorted_deterministically() -> None:
    snapshot = merge_snapshot(
        {"zeta": _api("zeta"), "alpha": _api("alpha")},
        {"mid": _console("mid")},
        None,
        now=NOW,
    )
    assert list(snapshot["models"]) == ["alpha", "mid", "zeta"]


def test_is_free_or_from_console() -> None:
    console = _console("alpha")
    console = ConsoleModel(
        key="alpha", name="ALPHA", go_allowance="$60", go_plus_allowance="$120",
        badges=(), is_free=True,
    )
    snapshot = merge_snapshot({"alpha": _api("alpha")}, {"alpha": console}, None, now=NOW)
    assert snapshot["models"]["alpha"]["is_free"] is True
