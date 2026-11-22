"""Self-contained, accessible static HTML page generation.

Design notes:
- Single file: inline ``<style>`` and one inline vanilla-JS table sorter.
  No external requests, web fonts, scripts, or frameworks.
- Monospace design: the system mono stack is the page font.
- MaintainableCSS: semantic lowerCamelCase module classes
  (``.module-component``), flat single-class selectors, ``@media`` co-located
  with the owning module.
- Cascade layers: ``reset, tokens, base, layout, components``.
- Collapsible tables: every table ships inside a closed ``<details>``
  panel; opening needs no JavaScript.
- Sortable tables: each column header holds a ``<button>`` and the ``<th>``
  carries ``aria-sort``; the inline script sorts rows by ``data-value``.
- WCAG 2.2 AA: skip link, landmarks, table captions, ``th scope``, scrollable
  regions with ``role="region"``, ``<time>`` stamps, text labels for badges
  (never colour alone), and contrast-checked light/dark tokens.
"""

from __future__ import annotations

import html
from datetime import date
from typing import Any

from .config import Settings
from .models import HistoryEntry, ModelEntry, Snapshot

# Days a model stays flagged New, or a change stays flagged Recently changed.
RECENT_WINDOW_DAYS = 7

_STYLESHEET = """
@layer reset, tokens, base, layout, components;

@layer reset {
  *, *::before, *::after { box-sizing: border-box; }
  body, h1, h2, h3, p, ul, ol, figure { margin: 0; }
  ul, ol { padding: 0; list-style: none; }
  table { border-collapse: collapse; }
}

@layer tokens {
  :root {
    color-scheme: light dark;
    --color-bg: #ffffff;
    --color-surface: #f7f7f7;
    --color-text: #1a1a1a;
    --color-text-muted: #565656;
    --color-border: #767676;
    --color-accent: #0b57d0;
    --color-notice-bg: #fff4d6;
    --color-hot-bg: #ffedd8;
    --color-new-bg: #e4f3e4;
    --color-changed-bg: #e3eefc;
    --font-mono: ui-monospace, "Cascadia Mono", SFMono-Regular, Menlo,
                 Consolas, "DejaVu Sans Mono", monospace;
    --space-s: 0.5rem;
    --space-m: 0.75rem;
    --space-l: 1.25rem;
    --space-xl: 2rem;
    --radius-s: 4px;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --color-bg: #141414;
      --color-surface: #1e1e1e;
      --color-text: #f2f2f2;
      --color-text-muted: #b0b0b0;
      --color-border: #6e6e6e;
      --color-accent: #a8c7fa;
      --color-notice-bg: #2b2617;
      --color-hot-bg: #2b2114;
      --color-new-bg: #152318;
      --color-changed-bg: #14202e;
    }
  }
}

@layer base {
  body {
    font-family: var(--font-mono);
    font-size: 0.9375rem;
    line-height: 1.5;
    background: var(--color-bg);
    color: var(--color-text);
  }

  h1 { font-size: 1.5rem; line-height: 1.25; }
  h2 { font-size: 1.25rem; line-height: 1.3; }
  h3 { font-size: 1rem; line-height: 1.4; }

  a { color: var(--color-accent); }

  :focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }
}

@layer layout {
  .page {
    max-width: 72rem;
    margin: 0 auto;
    padding: var(--space-l);
  }

  .page > * + * { margin-top: var(--space-xl); }
}

@layer components {
  .skipLink {
    position: absolute;
    left: -9999px;
    padding: var(--space-s) var(--space-m);
    background: var(--color-bg);
    color: var(--color-accent);
  }

  .skipLink:focus { left: var(--space-l); }

  .pageHeader-title { margin-top: var(--space-s); }
  .pageHeader-meta { color: var(--color-text-muted); }
  .pageHeader-meta + .pageHeader-meta { margin-top: var(--space-s); }

  .statusBanner {
    padding: var(--space-m);
    background: var(--color-notice-bg);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-s);
  }

  .tablePanel {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-s);
  }

  .tablePanel-toggle {
    display: block;
    padding: var(--space-m);
    cursor: pointer;
    list-style: revert;
  }

  .tablePanel-toggle::-webkit-details-marker { display: none; }
  .tablePanel-toggle::before { content: "\\25B8 "; }
  .tablePanel[open] > .tablePanel-toggle::before { content: "\\25BE "; }

  .tableScroll {
    overflow-x: auto;
  }

  .dealsTable, .freeTable, .modelsTable { width: 100%; }

  .dealsTable caption, .freeTable caption, .modelsTable caption {
    padding: 0 var(--space-m) var(--space-m);
    text-align: left;
    color: var(--color-text-muted);
  }

  .dealsTable th, .dealsTable td,
  .freeTable th, .freeTable td,
  .modelsTable th, .modelsTable td {
    padding: var(--space-s) var(--space-m);
    border-top: 1px solid var(--color-border);
    text-align: left;
    vertical-align: top;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .dealsTable-sort, .freeTable-sort, .modelsTable-sort {
    all: unset;
    cursor: pointer;
    font: inherit;
  }

  .dealsTable-sort:hover, .freeTable-sort:hover, .modelsTable-sort:hover,
  .dealsTable-sort:focus-visible, .freeTable-sort:focus-visible,
  .modelsTable-sort:focus-visible {
    text-decoration: underline;
  }

  .dealsTable-badges, .freeTable-badges, .modelsTable-badges {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-s);
    white-space: normal;
  }

  .modelsTable-row--hot { background: var(--color-hot-bg); }
  .modelsTable-row--new { background: var(--color-new-bg); }
  .modelsTable-row--changed { background: var(--color-changed-bg); }

  .dealsTable-badge, .freeTable-badge, .modelsTable-badge {
    padding: 0.125rem var(--space-s);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-s);
    font-size: 0.8125rem;
    white-space: nowrap;
  }

  .emptyState {
    padding: var(--space-m);
    border-top: 1px solid var(--color-border);
    color: var(--color-text-muted);
  }

  .changesLog-entry + .changesLog-entry { margin-top: var(--space-l); }

  .changesLog-entryTitle { margin-bottom: var(--space-s); }

  .changesLog-detail + .changesLog-detail { margin-top: var(--space-s); }

  .changesLog-item { color: var(--color-text); }
  .changesLog-item + .changesLog-item { margin-top: var(--space-s); }

  .pageFooter {
    padding-top: var(--space-l);
    border-top: 1px solid var(--color-border);
    color: var(--color-text-muted);
  }

  .pageFooter-links { margin-top: var(--space-s); }
}
"""

_SCRIPT = """
"use strict";
function sortValue(cell, type) {
  const raw = cell.dataset.value !== undefined ? cell.dataset.value
    : cell.textContent.trim();
  if (type === "num") {
    const number = Number.parseFloat(raw);
    return Number.isFinite(number) ? number : -Infinity;
  }
  return raw.toLowerCase();
}
document.querySelectorAll("table").forEach(function (table) {
  const body = table.tBodies[0];
  if (!body || !table.tHead) { return; }
  const headers = Array.from(table.tHead.rows[0].cells);
  headers.forEach(function (th, index) {
    const button = th.querySelector("button");
    if (!button) { return; }
    button.addEventListener("click", function () {
      const direction = th.getAttribute("aria-sort") === "ascending"
        ? "descending" : "ascending";
      headers.forEach(function (other) {
        other.setAttribute("aria-sort", "none");
      });
      th.setAttribute("aria-sort", direction);
      const type = button.dataset.sortType || "text";
      const rows = Array.from(body.rows);
      rows.sort(function (a, b) {
        const left = sortValue(a.cells[index], type);
        const right = sortValue(b.cells[index], type);
        const order = left < right ? -1 : left > right ? 1 : 0;
        return direction === "ascending" ? order : -order;
      });
      rows.forEach(function (row) { body.appendChild(row); });
    });
  });
});
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fmt_cost(value: float | None) -> str:
    return "—" if value is None else f"${value:.2f}"


def _cost_sort_value(value: float | None) -> str:
    return "-Infinity" if value is None else str(value)


def _fmt_int(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def _int_sort_value(value: int | None) -> str:
    return "-Infinity" if value is None else str(value)


def _allowance_sort_value(value: str | None) -> str:
    if value is None:
        return "-Infinity"
    if "∞" in value:
        return "Infinity"
    digits = value.replace("$", "").replace(",", "")
    return digits or "-Infinity"


def _allowance_float(value: str | None) -> float:
    return float(_allowance_sort_value(value))


def _order_by_allowance(entries: list[ModelEntry]) -> list[ModelEntry]:
    """Default order: the most generous Go allowances rise to the top."""
    return sorted(
        entries,
        key=lambda entry: (
            -_allowance_float(entry["go_allowance"]),
            entry["name"].casefold(),
        ),
    )


def _top_allowance_keys(entries: list[ModelEntry], limit: int = 10) -> set[str]:
    """Keys of the hottest paid models: the 10 largest Go allowances, ties kept.

    Free tiers are excluded: the Free badge already marks them.
    """
    paid = [
        entry
        for entry in entries
        if not entry["is_free"] and entry["go_allowance"] is not None
    ]
    if not paid:
        return set()
    ranked = _order_by_allowance(paid)
    cutoff = _allowance_float(ranked[min(limit, len(ranked)) - 1]["go_allowance"])
    return {
        entry["key"]
        for entry in paid
        if _allowance_float(entry["go_allowance"]) >= cutoff
    }


def _days_before(today: str, date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        parsed_today = date.fromisoformat(today)
        parsed = date.fromisoformat(date_str)
    except ValueError:
        return None
    return (parsed_today - parsed).days


def _is_within_window(today: str, date_str: str | None) -> bool:
    days = _days_before(today, date_str)
    return days is not None and days <= RECENT_WINDOW_DAYS


def _computed_flags(
    entry: ModelEntry, today: str, baseline_date: str | None
) -> list[str]:
    """New and Recently changed labels for the All tracked models table.

    ``New`` marks models that first appeared after monitoring began (the
    baseline date), so the starting inventory never lights up. The label
    holds for ``RECENT_WINDOW_DAYS`` days.
    """
    flags: list[str] = []
    seen_after_baseline = baseline_date is None or entry["first_seen"] > baseline_date
    if seen_after_baseline and _is_within_window(today, entry["first_seen"]):
        flags.append("New")
    last_changed = entry.get("last_changed")
    changed_after_first_seen = last_changed and last_changed > entry["first_seen"]
    if changed_after_first_seen and _is_within_window(today, last_changed):
        flags.append("Recently changed")
    return flags


def _fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    return f'<time datetime="{_esc(value)}">{_esc(value)}</time>'


def _date_sort_value(value: str | None) -> str:
    return value or ""


def _badges(entry: ModelEntry, module: str) -> str:
    badges = list(entry["badges"])
    if entry["is_free"] and "Free" not in badges:
        badges.append("Free")
    if not badges:
        return "—"
    spans = "".join(
        f'<span class="{module}-badge">{_esc(badge)}</span>' for badge in badges
    )
    return f'<span class="{module}-badges">{spans}</span>'


def _th(label: str, module: str, sort_type: str, *, default: str = "none") -> str:
    return (
        f'<th scope="col" aria-sort="{default}">'
        f'<button type="button" class="{module}-sort" '
        f'data-sort-type="{sort_type}">{_esc(label)}</button></th>'
    )


def _td(content: str, *, value: str | None = None) -> str:
    data = f' data-value="{_esc(value)}"' if value is not None else ""
    return f"<td{data}>{content}</td>"


def _is_promo(entry: ModelEntry) -> bool:
    return bool(entry["badges"]) and not entry["is_free"]


def _deal_row(entry: ModelEntry, module: str) -> str:
    go = _esc(entry["go_allowance"] or "—")
    go_plus = _esc(entry["go_plus_allowance"] or "—")
    go_value = _allowance_sort_value(entry["go_allowance"])
    go_plus_value = _allowance_sort_value(entry["go_plus_allowance"])
    badges = " ".join(entry["badges"])
    in_cost = _fmt_cost(entry["input_cost_per_m"])
    out_cost = _fmt_cost(entry["output_cost_per_m"])
    in_value = _cost_sort_value(entry["input_cost_per_m"])
    out_value = _cost_sort_value(entry["output_cost_per_m"])
    since = _fmt_date(entry["allowance_since"])
    since_value = _date_sort_value(entry["allowance_since"])
    return (
        f'<tr><th scope="row">{_esc(entry["name"])}</th>'
        f"{_td(go, value=go_value)}"
        f"{_td(go_plus, value=go_plus_value)}"
        f"{_td(_badges(entry, module), value=badges)}"
        f"{_td(in_cost, value=in_value)}"
        f"{_td(out_cost, value=out_value)}"
        f"{_td(since, value=since_value)}"
        f"</tr>"
    )


def _model_row(
    entry: ModelEntry,
    today: str,
    hot_keys: set[str],
    baseline_date: str | None,
) -> str:
    providers = ", ".join(entry["providers"]) or "—"
    go = _esc(entry["go_allowance"] or "—")
    go_plus = _esc(entry["go_plus_allowance"] or "—")
    go_value = _allowance_sort_value(entry["go_allowance"])
    go_plus_value = _allowance_sort_value(entry["go_plus_allowance"])
    context = _fmt_int(entry["context_limit"])
    output = _fmt_int(entry["output_limit"])
    context_value = _int_sort_value(entry["context_limit"])
    output_value = _int_sort_value(entry["output_limit"])
    in_cost = _fmt_cost(entry["input_cost_per_m"])
    out_cost = _fmt_cost(entry["output_cost_per_m"])
    in_value = _cost_sort_value(entry["input_cost_per_m"])
    out_value = _cost_sort_value(entry["output_cost_per_m"])
    flags = _computed_flags(entry, today, baseline_date)
    badges = [*entry["badges"], *flags]
    if entry["is_free"]:
        badges.append("Free")
    if entry["key"] in hot_keys:
        badges.append("Top allowance")
    badges = list(dict.fromkeys(badges))  # dedupe, preserve order
    hot_class = " modelsTable-row--hot" if entry["key"] in hot_keys else ""
    if "New" in flags:
        hot_class += " modelsTable-row--new"
    if "Recently changed" in flags:
        hot_class += " modelsTable-row--changed"
    badge_spans = "".join(
        f'<span class="modelsTable-badge">{_esc(badge)}</span>' for badge in badges
    ) or "—"
    badge_block = (
        f'<span class="modelsTable-badges">{badge_spans}</span>'
        if badge_spans != "—"
        else badge_spans
    )
    return (
        f'<tr class="modelsTable-row{hot_class}">'
        f'<th scope="row">{_esc(entry["name"])}</th>'
        f"{_td(go, value=go_value)}"
        f"{_td(go_plus, value=go_plus_value)}"
        f"{_td(badge_block, value=' '.join(entry['badges']))}"
        f"{_td(in_cost, value=in_value)}"
        f"{_td(out_cost, value=out_value)}"
        f'{_td(_esc(entry["id"]))}'
        f"{_td(_esc(providers), value=providers)}"
        f"{_td(context, value=context_value)}"
        f"{_td(output, value=output_value)}"
        f'{_td(_fmt_date(entry["first_seen"]), value=_date_sort_value(entry["first_seen"]))}'
        f'{_td(_fmt_date(entry["last_changed"]), value=_date_sort_value(entry["last_changed"]))}'
        f"</tr>"
    )


def _deal_table(
    entries: list[ModelEntry],
    heading_id: str,
    module: str,
    caption: str,
    empty_text: str,
) -> str:
    if not entries:
        return f'<p class="emptyState">{_esc(empty_text)}</p>'
    head = (
        f'<tr>{_th("Model", module, "text")}'
        f"{_th('Go', module, 'num', default='descending')}"
        f"{_th('Go Plus', module, 'num')}"
        f"{_th('Badges', module, 'text')}"
        f"{_th('In $/M', module, 'num')}"
        f"{_th('Out $/M', module, 'num')}"
        f"{_th('Active since', module, 'text')}</tr>"
    )
    rows = "".join(_deal_row(entry, module) for entry in _order_by_allowance(entries))
    table = (
        f'<table class="{module}">'
        f"<caption>{_esc(caption)}</caption>"
        f"<thead>{head}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table>"
    )
    return (
        f'<div class="tableScroll" tabindex="0" role="region" '
        f'aria-labelledby="{heading_id}">{table}</div>'
    )


def _all_models_table(
    entries: list[ModelEntry], today: str, baseline_date: str | None
) -> str:
    head = (
        f'<tr>{_th("Model", "modelsTable", "text")}'
        f'{_th("Go", "modelsTable", "num", default="descending")}'
        f'{_th("Go Plus", "modelsTable", "num")}'
        f'{_th("Badges", "modelsTable", "text")}'
        f'{_th("In $/M", "modelsTable", "num")}'
        f'{_th("Out $/M", "modelsTable", "num")}'
        f'{_th("ID", "modelsTable", "text")}'
        f'{_th("Providers", "modelsTable", "text")}'
        f'{_th("Context", "modelsTable", "num")}'
        f'{_th("Output cap", "modelsTable", "num")}'
        f'{_th("First seen", "modelsTable", "text")}'
        f'{_th("Last changed", "modelsTable", "text")}</tr>'
    )
    ordered = _order_by_allowance(entries)
    hot_keys = _top_allowance_keys(entries)
    rows = "".join(
        _model_row(entry, today, hot_keys, baseline_date) for entry in ordered
    )
    return (
        f'<div class="tableScroll" tabindex="0" role="region" '
        f'aria-labelledby="all-models-heading">'
        f'<table class="modelsTable">'
        f"<caption>All tracked models from models.dev and the Go console. "
        f"Top allowance marks the 10 paid models with the largest Go monthly "
        f"allowance. New and Recently changed mark models from the last "
        f"{RECENT_WINDOW_DAYS} days. Rows start sorted by Go allowance.</caption>"
        f"<thead>{head}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


def _panel(heading_id: str, title: str, inner: str) -> str:
    # Tables ship collapsed: no `open` attribute, so the page opens small.
    return (
        f'<details class="tablePanel">'
        f'<summary class="tablePanel-toggle">'
        f'<h2 id="{heading_id}">{_esc(title)}</h2></summary>'
        f"{inner}</details>"
    )


def _banner(snapshot: Snapshot) -> str:
    verified = snapshot["console_html_verified_at"]
    if not snapshot["console_html_degraded"]:
        return ""
    when = _fmt_date((verified or "").split("T")[0]) if verified else "an earlier check"
    return (
        f'<div class="statusBanner" role="status">'
        f"<p>Go and Go Plus allowances could not be refreshed. "
        f"The figures below are carried forward from the last successful check "
        f"on {when}.</p></div>"
    )


def _changes_log(history: list[HistoryEntry]) -> str:
    if not history:
        return '<p class="emptyState">No changes recorded yet.</p>'
    items: list[str] = []
    for entry in reversed(history):
        details: list[str] = []
        if entry["added"]:
            starting = "".join(f"<li>{_esc(name)}</li>" for name in entry["added"])
            details.append(f"<p>Starting:</p><ul>{starting}</ul>")
        for change in entry["changed"]:
            label = change["field"].replace("_", " ")
            details.append(
                f'<ul><li class="changesLog-item">{_esc(change["key"])}: '
                f"{label} {_esc(change['old'])} &rarr; {_esc(change['new'])}</li></ul>"
            )
        if entry["removed"]:
            ended = "".join(f"<li>{_esc(name)}</li>" for name in entry["removed"])
            details.append(f"<p>Ended:</p><ul>{ended}</ul>")
        if not details:
            continue
        timestamp = entry["timestamp"]
        items.append(
            f'<li class="changesLog-entry">'
            f'<h3 class="changesLog-entryTitle">{_esc(entry["title"])}: '
            f'<time datetime="{_esc(timestamp)}">{_esc(timestamp)}</time></h3>'
            f'<div class="changesLog-detail">{"".join(details)}</div>'
            f"</li>"
        )
    if not items:
        return '<p class="emptyState">No changes recorded yet.</p>'
    return f'<ol class="changesLog">{"".join(items)}</ol>'


def build_page(snapshot: Snapshot, history: list[HistoryEntry], settings: Settings) -> str:
    """Render the full self-contained status page."""
    models = snapshot["models"]
    promo_entries = [entry for entry in models.values() if _is_promo(entry)]
    free_entries = [entry for entry in models.values() if entry["is_free"]]
    updated = snapshot["updated_at"]
    today = updated.split("T")[0]
    baseline_date = history[0]["timestamp"].split("T")[0] if history else None
    promos = _deal_table(
        promo_entries,
        "promos-heading",
        "dealsTable",
        "Models with an active promotion",
        "No active promotions right now.",
    )
    frees = _deal_table(
        free_entries,
        "free-heading",
        "freeTable",
        "Models with a free tier",
        "No free models right now.",
    )
    all_models = _all_models_table(list(models.values()), today, baseline_date)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(settings.feed_title)}</title>
<link rel="alternate" type="application/atom+xml" title="OpenCode Go Deals" href="feed.xml">
<style>{_STYLESHEET}</style>
</head>
<body>
<a class="skipLink" href="#main-content">Skip to main content</a>
<div class="page">
<header class="pageHeader">
<h1 class="pageHeader-title">{_esc(settings.feed_title)}</h1>
<p class="pageHeader-meta">Last updated <time datetime="{_esc(updated)}">{_esc(updated)}</time></p>
<p class="pageHeader-meta">Subscribe: <a href="feed.xml">Atom feed</a></p>
</header>
<main id="main-content">
{_banner(snapshot)}
{_panel("promos-heading", "Promos", promos)}
{_panel("free-heading", "Free models", frees)}
{_panel("all-models-heading", "All tracked models", all_models)}
<section aria-labelledby="changes-heading">
<h2 id="changes-heading">Recent changes</h2>
{_changes_log(history)}
</section>
</main>
<footer class="pageFooter">
<p>Data: <a href="deals.json">deals.json</a>
&middot; sources: models.dev and the OpenCode Go console.</p>
</footer>
</div>
<script>{_SCRIPT}</script>
</body>
</html>
"""
