"""Dataclasses, TypedDicts, and shared normalisation for snapshots and diffs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TypedDict


def normalise_key(value: str) -> str:
    """Normalise a model name or ID for joining sources.

    Lowercases and strips punctuation and whitespace so that
    ``GLM-5.3-Flash`` and ``glm-5.3-flash`` both become ``glm53flash``.
    """
    lowered = value.casefold()
    stripped = re.sub(r"[^a-z0-9]+", "", lowered)
    return stripped


def allowance_value(value: str | None) -> float:
    """Numeric sort/significance value for an allowance: ``∞`` is infinite."""
    if value is None:
        return float("-inf")
    if "∞" in value:
        return float("inf")
    digits = value.replace("$", "").replace(",", "")
    try:
        return float(digits)
    except ValueError:
        return float("-inf")


def artificial_analysis_url(name: str) -> str:
    """Best-guess Artificial Analysis page for a model display name."""
    slug = name.casefold().replace(".", "-")
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"https://artificialanalysis.ai/models/{slug}"


@dataclass(frozen=True, slots=True)
class ApiModel:
    """A model parsed from models.dev/api.json."""

    key: str
    id: str
    name: str
    providers: tuple[str, ...]
    context_limit: int | None
    output_limit: int | None
    input_cost_per_m: float | None
    output_cost_per_m: float | None
    is_free: bool


@dataclass(frozen=True, slots=True)
class ConsoleModel:
    """A model parsed from the OpenCode Go console page."""

    key: str
    name: str
    go_allowance: str | None
    go_plus_allowance: str | None
    badges: tuple[str, ...]
    is_free: bool


class ModelEntry(TypedDict):
    """One model in the merged snapshot (data/state.json and public/deals.json)."""

    key: str
    id: str
    name: str
    providers: list[str]
    context_limit: int | None
    output_limit: int | None
    input_cost_per_m: float | None
    output_cost_per_m: float | None
    go_allowance: str | None
    go_plus_allowance: str | None
    badges: list[str]
    is_free: bool
    first_seen: str
    allowance_since: str | None
    last_changed: str | None
    last_trend: str | None
    info_url: str | None
    info_checked: str | None


class Snapshot(TypedDict):
    """The merged snapshot written to data/state.json and public/deals.json."""

    updated_at: str
    console_html_verified_at: str | None
    console_html_degraded: bool
    models: dict[str, ModelEntry]


@dataclass(frozen=True, slots=True)
class Change:
    """A single tracked-field change between two snapshots."""

    key: str
    field: str
    old: Any
    new: Any


@dataclass(frozen=True, slots=True)
class DiffResult:
    """Diff between the previous and current snapshot."""

    added: list[str] = field(default_factory=list)
    changed: list[Change] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.added and not self.changed and not self.removed


class HistoryEntry(TypedDict):
    """One diff event in data/history.json and the Atom feed."""

    id: str
    timestamp: str
    title: str
    added: list[str]
    changed: list[dict[str, Any]]
    removed: list[str]
    degraded: bool
    note: str
    names: dict[str, str]
