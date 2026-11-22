"""RFC 4287 Atom 1.0 feed generation, plus shared changelog formatting."""

from __future__ import annotations

import hashlib
import html
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from .config import Settings
from .models import HistoryEntry

ATOM_NS = "http://www.w3.org/2005/Atom"

ET.register_namespace("", ATOM_NS)

# Readable names for the tracked change fields, shared by the feed and the page.
FIELD_LABELS = {
    "go_allowance": "Go allowance",
    "go_plus_allowance": "Go Plus allowance",
    "input_cost_per_m": "Input price",
    "output_cost_per_m": "Output price",
    "is_free": "Free tier",
    "badges": "Badges",
}


def entry_id(timestamp: str, added: list[str], changed: list[Any], removed: list[str]) -> str:
    """Deterministic entry id so republished runs never duplicate entries.

    The hash covers the UTC date and the diff content, so the same change
    republished on the same day keeps its id.
    """
    date = timestamp.split("T")[0]
    digest = hashlib.sha256(
        "\x00".join(
            [
                date,
                *added,
                *[f"{c['key']}:{c['field']}:{c['old']}->{c['new']}" for c in changed],
                *removed,
            ]
        ).encode("utf-8")
    ).hexdigest()[:10]
    return f"urn:opencode-deals:{date}:{digest}"


def entry_anchor(history_id: str) -> str:
    """DOM anchor for a history entry, e.g. ``chg-2026-11-23-abc123``."""
    return history_id.replace("urn:opencode-deals:", "chg-").replace(":", "-")


def field_label(field: str) -> str:
    """Readable label for a tracked field."""
    return FIELD_LABELS.get(field, field.replace("_", " "))


def format_value(field: str, value: Any) -> str:
    """Readable value for a tracked field: no Python reprs, no raw ``None``."""
    if value is None:
        return "none"
    if field == "badges":
        items = [str(item) for item in value] if isinstance(value, list) else [str(value)]
        return ", ".join(items) if items else "none"
    if field == "is_free":
        return "yes" if value else "no"
    if field in {"input_cost_per_m", "output_cost_per_m"}:
        return f"${value:.2f}/M" if isinstance(value, (int, float)) else str(value)
    return str(value)


def format_timestamp(timestamp: str) -> str:
    """Human timestamp: ``2026-11-23T08:23:00Z`` -> ``23 November 2026, 08:23 UTC``."""
    try:
        stamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return timestamp
    return f"{stamp.day} {stamp.strftime('%B %Y')}, {stamp.strftime('%H:%M')} UTC"


def _escape(value: Any) -> str:
    return html.escape(_plain(value), quote=True)


def _plain(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_plain(item) for item in value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _entry_title(entry: HistoryEntry) -> str:
    if entry["title"]:
        return entry["title"]
    parts: list[str] = []
    if entry["added"]:
        parts.append(_plural(len(entry["added"]), "model started"))
    if entry["changed"]:
        parts.append(_plural(len(entry["changed"]), "change"))
    if entry["removed"]:
        parts.append(_plural(len(entry["removed"]), "model ended"))
    return ", ".join(parts) or "No changes"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _model_name(names: dict[str, str], key: str) -> str:
    return names.get(key) or key


def _entry_content_html(entry: HistoryEntry) -> str:
    names = entry.get("names") or {}
    lines: list[str] = []
    if entry.get("note"):
        lines.append(f"<p>{_escape(entry['note'])}</p>")
    if entry["added"]:
        lines.append("<p>Starting:</p>")
        lines.append("<ul>")
        lines.extend(f"<li>{_escape(_model_name(names, key))}</li>" for key in entry["added"])
        lines.append("</ul>")
    if entry["changed"]:
        lines.append("<p>Changed:</p>")
        lines.append("<ul>")
        for change in entry["changed"]:
            item = (
                f"{_escape(_model_name(names, change['key']))}: "
                f"{_escape(field_label(change['field']))} from "
                f"{_escape(format_value(change['field'], change['old']))} to "
                f"{_escape(format_value(change['field'], change['new']))}"
            )
            lines.append(f"<li>{item}</li>")
        lines.append("</ul>")
    if entry["removed"]:
        lines.append("<p>Ended:</p>")
        lines.append("<ul>")
        lines.extend(f"<li>{_escape(_model_name(names, key))}</li>" for key in entry["removed"])
        lines.append("</ul>")
    if entry["degraded"]:
        lines.append(
            "<p>Go and Go Plus allowances could not be refreshed in this run. "
            "The figures were carried forward from the last successful check.</p>"
        )
    return "\n".join(lines) or "<p>No changes.</p>"


def build_feed(entries: list[HistoryEntry], settings: Settings) -> str:
    """Render up to the latest history entries as an Atom 1.0 document."""
    feed = ET.Element("feed", {"xmlns": ATOM_NS})
    base = settings.public_base_url.rstrip("/")
    ET.SubElement(feed, "id").text = f"tag:{base}"
    ET.SubElement(feed, "title").text = settings.feed_title
    ET.SubElement(feed, "updated").text = (
        max(entry["timestamp"] for entry in entries) if entries else "1970-01-01T00:00:00Z"
    )
    ET.SubElement(
        feed,
        "link",
        {"rel": "self", "type": "application/atom+xml", "href": f"{base}/feed.xml"},
    )
    ET.SubElement(
        feed,
        "link",
        {"rel": "alternate", "type": "text/html", "href": f"{base}/"},
    )

    for entry in entries[-settings.history_limit :]:
        element = ET.SubElement(feed, "entry")
        ET.SubElement(element, "id").text = entry["id"]
        ET.SubElement(element, "title").text = _entry_title(entry)
        ET.SubElement(element, "updated").text = entry["timestamp"]
        ET.SubElement(
            element,
            "link",
            {
                "rel": "alternate",
                "type": "text/html",
                "href": f"{base}/#{entry_anchor(entry['id'])}",
            },
        )
        content = ET.SubElement(element, "content", {"type": "html"})
        content.text = _entry_content_html(entry)

    ET.indent(feed)
    return ET.tostring(feed, encoding="utf-8", xml_declaration=True).decode("utf-8")
