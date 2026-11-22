"""Parser for the opencode.ai/console/go models table.

The console page is server-rendered: each model is a ``<tr data-model="...">``
row with the display name in ``[data-layer="model-name"]``, Go / Go Plus
dollar allowances in the ``td[data-allowance-type="usage"]`` cell (mirrored
accessibly in its ``span.sr-only`` text), and promotional badges in
``.console-go-models-new`` and ``.console-go-models-note`` spans. No
hydration payload parsing is required. See README.md, "Data sources".
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import ConsoleModel, normalise_key

_ALLOWANCE_RE = re.compile(r"Go:\s*([^;]+);\s*Go Plus:\s*(.+)$")
_NOTE_SEPARATOR = "·"


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = " ".join(text.split())
    return cleaned or None


def _parse_allowances(usage_cell) -> tuple[str | None, str | None]:
    """Read Go / Go Plus allowances from the usage cell.

    The layered ``data-plan`` spans carry the display formatting (commas),
    while the ``sr-only`` mirror is the accessible plain-text form.
    """
    if usage_cell is None:
        return None, None
    go = usage_cell.find("span", {"data-plan": "go"})
    go_plus = usage_cell.find("span", {"data-plan": "go-plus"})
    if go is not None and go_plus is not None:
        return _clean(go.get_text()), _clean(go_plus.get_text())
    sr_only = usage_cell.find("span", class_="sr-only")
    if sr_only is not None:
        match = _ALLOWANCE_RE.search(" ".join(sr_only.get_text().split()))
        if match:
            return _clean(match.group(1)), _clean(match.group(2))
    return None, None


def _parse_badges(row) -> tuple[str, ...]:
    badges: list[str] = []
    for new_badge in row.find_all("span", class_="console-go-models-new"):
        text = _clean(new_badge.get_text())
        if text:
            badges.append(text)
    for note in row.find_all("span", class_="console-go-models-note"):
        text = _clean(note.get_text())
        if text:
            badges.extend(
                part.strip() for part in text.split(_NOTE_SEPARATOR) if part.strip()
            )
    # Preserve order, drop duplicates.
    return tuple(dict.fromkeys(badges))


def parse_console_html(html_text: str) -> dict[str, ConsoleModel]:
    """Extract the models table. Returns an empty map when nothing parses."""
    soup = BeautifulSoup(html_text, "html.parser")
    models: dict[str, ConsoleModel] = {}
    for row in soup.find_all("tr", attrs={"data-model": True}):
        row_id = row["data-model"]
        if not isinstance(row_id, str):
            continue
        key = normalise_key(row_id)
        name_span = row.find("span", attrs={"data-layer": "model-name"})
        name_source = name_span or row.th
        name = _clean(name_source.get_text()) if name_source else row_id
        usage_cell = row.find("td", attrs={"data-allowance-type": "usage"})
        go_allowance, go_plus_allowance = _parse_allowances(usage_cell)
        badges = _parse_badges(row)
        infinite = go_allowance in {"∞", "$∞"} and go_plus_allowance in {"∞", "$∞"}
        models[key] = ConsoleModel(
            key=key,
            name=name or row_id,
            go_allowance=go_allowance,
            go_plus_allowance=go_plus_allowance,
            badges=badges,
            is_free=key.endswith("free") or infinite,
        )
    return models
