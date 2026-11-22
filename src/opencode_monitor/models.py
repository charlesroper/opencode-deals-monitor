"""Dataclasses, TypedDicts, and shared normalisation for snapshots and diffs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TypedDict
from urllib.parse import quote_plus


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


def duckduckgo_ai_url(name: str) -> str:
    """DuckDuckGo AI search for a model without a verified review page.

    Lands on the AI chat tab with a prompt that asks for a sourced summary,
    so the answer is grounded in search results.
    """
    prompt = (
        f"What is {name}? Summarise its context window, price and coding "
        "benchmarks, plus community opinion and sentiment from Hacker News, "
        "Lobsters, Reddit and similar sites. Cite sources."
    )
    return "https://duckduckgo.com/?q=" + quote_plus(prompt) + "&ia=chat&prompt=1"


def _model_slug(name: str) -> str:
    """URL slug shared by review sites: lowercased, dots and spaces dashed."""
    slug = name.casefold().replace(".", "-")
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def artificial_analysis_url(name: str) -> str:
    """Artificial Analysis page URL for a model display name."""
    return f"https://artificialanalysis.ai/models/{_model_slug(name)}"


def epoch_ai_url(name: str) -> str:
    """Epoch AI model page URL for a model display name."""
    return f"https://epoch.ai/models/{_model_slug(name)}"


def opencode_model_url(canonical_model_id: str | None) -> str | None:
    """OpenCode model page URL from a models.dev canonical id.

    ``deepseek/deepseek-v4.1-flash`` becomes
    ``opencode.ai/data/deepseek/deepseek-v4-1-flash``.
    """
    if not canonical_model_id:
        return None
    org, _, model = canonical_model_id.partition("/")
    if not org or not model:
        return None
    return f"https://opencode.ai/data/{_model_slug(org)}/{_model_slug(model)}"


@dataclass(frozen=True, slots=True)
class ApiModel:
    """A model parsed from models.dev/api.json."""

    key: str
    id: str
    name: str
    canonical_model_id: str | None
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
    canonical_model_id: str | None
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
    epoch_url: str | None
    epoch_checked: str | None
    opencode_url: str | None
    opencode_checked: str | None


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
