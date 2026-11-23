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

from .atom_builder import entry_anchor, field_label, format_timestamp, format_value
from .config import Settings
from .differ import change_direction
from .models import HistoryEntry, ModelEntry, Snapshot, duckduckgo_ai_url

# Days a model stays flagged New, or a change stays flagged Recently changed.
RECENT_WINDOW_DAYS = 7

# Inline destination icons (Artificial Analysis, DuckDuckGo). Embedded as
# data URIs so the page keeps making no external asset requests.
_FAVICON_AA = (
    "data:image/png;base64,"
    "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"
)

_FAVICON_DDG = (
    "data:image/png;base64,"
    "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"
)


_FAVICON_EPOCH = (
    "data:image/svg+xml;base64,"
    "PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+Cjxz"
    "dmcKICAgd2lkdGg9IjMyIgogICBoZWlnaHQ9IjMyIgogICB2aWV3Qm94PSIwIDAgMzIgMzIiCiAg"
    "IGZpbGw9Im5vbmUiCiAgIHZlcnNpb249IjEuMSIKICAgaWQ9InN2ZzQiCiAgIHNvZGlwb2RpOmRv"
    "Y25hbWU9ImZhdmljb24uc3ZnIgogICBpbmtzY2FwZTp2ZXJzaW9uPSIxLjEuMiAoMGEwMGNmNTMz"
    "OSwgMjAyMi0wMi0wNCkiCiAgIGlua3NjYXBlOmV4cG9ydC1maWxlbmFtZT0iL2hvbWUvZWR1L1By"
    "b2plY3RzL0Vwb2NoL2Rldi1lcG9jaC13ZWJzaXRlL2Fzc2V0cy9pbWFnZXMvZmF2aWNvbi5wbmci"
    "CiAgIGlua3NjYXBlOmV4cG9ydC14ZHBpPSIyOTkuOTMyMDEiCiAgIGlua3NjYXBlOmV4cG9ydC15"
    "ZHBpPSIyOTkuOTMyMDEiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9y"
    "Zy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2Rp"
    "LnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zPSJodHRwOi8vd3d3"
    "LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2"
    "ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczgiIC8+CiAgPHNvZGlwb2RpOm5hbWVkdmlldwogICAg"
    "IGlkPSJuYW1lZHZpZXc2IgogICAgIHBhZ2Vjb2xvcj0iI2ZmZmZmZiIKICAgICBib3JkZXJjb2xv"
    "cj0iIzY2NjY2NiIKICAgICBib3JkZXJvcGFjaXR5PSIxLjAiCiAgICAgaW5rc2NhcGU6cGFnZXNo"
    "YWRvdz0iMiIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMC4wIgogICAgIGlua3NjYXBlOnBh"
    "Z2VjaGVja2VyYm9hcmQ9IjAiCiAgICAgc2hvd2dyaWQ9ImZhbHNlIgogICAgIGlua3NjYXBlOnpv"
    "b209IjEwLjI0ODA0OCIKICAgICBpbmtzY2FwZTpjeD0iMTYuNDkwOTQ1IgogICAgIGlua3NjYXBl"
    "OmN5PSIxOS4xNzQzODMiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIxMjgwIgogICAgIGlu"
    "a3NjYXBlOndpbmRvdy1oZWlnaHQ9Ijc4MiIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iMCIKICAg"
    "ICBpbmtzY2FwZTp3aW5kb3cteT0iMTgiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0i"
    "MSIKICAgICBpbmtzY2FwZTpjdXJyZW50LWxheWVyPSJzdmc0IiAvPgogIDxwYXRoCiAgICAgZmls"
    "bC1ydWxlPSJldmVub2RkIgogICAgIGNsaXAtcnVsZT0iZXZlbm9kZCIKICAgICBkPSJNIDMuNDQx"
    "ODUsMjAuNTQzMjkxIDMwLjYwMDEsNy44NzkxNTEgQyAzMS40NTQxLDcuNDgwOTIxIDMyLDYuNjIz"
    "OTgxIDMyLDUuNjgxNzAxIDMyLDMuOTA3NzMxIDMwLjE1NzQsMi43MzQzMzEgMjguNTQ5OSwzLjQ4"
    "NDYwMSBMIDEuMzk2MTIsMTYuMTU4MjkxIEMgMC41NDQzOTYsMTYuNTU1ODkxIDAsMTcuNDEwNjkx"
    "IDAsMTguMzUwNTkxIGMgMCwxLjc2OTggMS44Mzc5MSwyLjk0MDcgMy40NDE4NSwyLjE5MjcgeiBt"
    "IDIwLjQwMDA1LC00LjQ5NjkgLTIyLjQ0NTIsMTAuNDY2NCBDIDAuNTQ0Njc0LDI2LjkxMDA5MSAw"
    "LDI3Ljc2NTA5MSAwLDI4LjcwNTE5MSBjIDAsMS43Njk1IDEuODM3NjUsMi45NDAyIDMuNDQxMzcs"
    "Mi4xOTI0IGwgMjIuNDQ1MjMsLTEwLjQ2NjQgYyAwLjg1MiwtMC4zOTczIDEuMzk2NywtMS4yNTIz"
    "IDEuMzk2NywtMi4xOTI0IDAsLTEuNzY5NSAtMS44Mzc3LC0yLjk0MDIgLTMuNDQxNCwtMi4xOTI0"
    "IHogTSAxMS40ODA4LDEuMTAyNDI0IDEuMzk2Nyw1LjgwNDcyMSBDIDAuNTQ0Njc0LDYuMjAyMDMx"
    "IDAsNy4wNTcwMDEgMCw3Ljk5NzExMSBjIDAsMS43Njk1MiAxLjgzNzY1LDIuOTQwMTggMy40NDEz"
    "NywyLjE5MjQgbCAxMC4wODQwMywtNC43MDIzIGMgMC44NTIxLC0wLjM5NzMxIDEuMzk2NywtMS4y"
    "NTIyOCAxLjM5NjcsLTIuMTkyNCAwLC0xLjc2OTUxIC0xLjgzNzYsLTIuOTQwMjE4NyAtMy40NDEz"
    "LC0yLjE5MjM4NyB6IgogICAgIGZpbGw9IiNFNkZFRjMiCiAgICAgaWQ9InBhdGgyIgogICAgIHN0"
    "eWxlPSJmaWxsOiMwMGE1YTY7ZmlsbC1vcGFjaXR5OjEiIC8+Cjwvc3ZnPgo="
)


_FAVICON_OPENCODE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABh0lEQVR42u2XS26DMBCG/wHbG5uH"
    "BHdhm6g9W3OpVhwosCBZAp2ujMjTBkLZxJI3YYg///OEsjRlbLgCbLw2BxAuAyJadAAzLwNo23bZ"
    "DYWYD0BEyPIcwUwVfplxapqnKohHB7dtiyzL8FOWSJIEzOztDmvbNA0+djvUdQ0p5V0QpwJ5nsMY"
    "M0sBKaUT2isGmHm4lesPx7Y+8eOVBfZQZkbzxKdEhDiOh3d8XCZ85bQ+/dzvb3w6jpnvskSapq+r"
    "A9fy1nWN4/F4F8An7xcB2Ly2ewzAzM6cfwmAlHLYYwD7bFWAMAxRFAVO5/ONAl3XIY4ihGG4sgJK"
    "QSl1AxAEAaRS67vA5rnd17+/54HVXXCvyk2pfIsB+r5H13UXRcdmQd/36wIQEbTWQ9G5BtBaT1ZB"
    "TIl+Ywy+Dgc8inUCoI2ZNDuIKWlHRDBR5GXv2xecAHao8L3R2NanNAvXbaqqGoaSOSOZSwV69mVE"
    "RIiT5P+H0ov+X1XbjeVzW+xLP0zmNJh3M5qy/gArfue1qzV+HwAAAABJRU5ErkJggg=="
)


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
    --color-notice-bg: #fff4d6;
    --color-tier1-bg: #ffd9a0;
    --color-tier2-bg: #ffe8c2;
    --color-tier3-bg: #fff1da;
    --color-tier4-bg: #fdf6e9;
    --color-tier5-bg: #fbfcf7;
    --color-new-bg: #e4f3e4;
    --color-changed-bg: #e3eefc;
    --color-up: #1a7f37;
    --color-down: #cf222e;
    --font-mono: ui-monospace, "Cascadia Mono", SFMono-Regular, Menlo,
                 Consolas, "DejaVu Sans Mono", monospace;
    --space-xs: 0.25rem;
    --space-s: 0.5rem;
    --space-m: 0.75rem;
    --space-l: 1.25rem;
    --space-xl: 1.5rem;
    --radius-s: 4px;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --color-bg: #141414;
      --color-surface: #1e1e1e;
      --color-text: #f2f2f2;
      --color-text-muted: #b0b0b0;
      --color-border: #6e6e6e;
      --color-notice-bg: #2b2617;
      --color-tier1-bg: #3a2c10;
      --color-tier2-bg: #30250f;
      --color-tier3-bg: #271e0e;
      --color-tier4-bg: #1f180c;
      --color-tier5-bg: #191509;
      --color-new-bg: #152318;
      --color-changed-bg: #14202e;
      --color-up: #3fb950;
      --color-down: #f85149;
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

  p + p { margin-top: var(--space-s); }

  a { color: var(--color-text); text-decoration: underline; }

  :focus-visible {
    outline: 2px solid var(--color-text);
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

  main > * + * { margin-top: var(--space-xl); }

  @media (max-width: 40rem) {
    .page { padding: var(--space-m); }
    .page > * + * { margin-top: var(--space-l); }
    main > * + * { margin-top: var(--space-l); }
  }
}

@layer components {
  .skipLink {
    position: absolute;
    left: -9999px;
    padding: var(--space-s) var(--space-m);
    background: var(--color-bg);
    color: var(--color-text);
  }

  .skipLink:focus { left: var(--space-l); }

  .pageHeader-title { margin-top: var(--space-s); }
  .pageHeader-meta { color: var(--color-text-muted); font-size: 0.875rem; }
  .pageHeader-meta + .pageHeader-meta { margin-top: var(--space-xs); }

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
    display: flex;
    align-items: center;
    gap: var(--space-s);
    padding: var(--space-s) var(--space-m);
    cursor: pointer;
    list-style: none;
  }

  .tablePanel-toggle:hover { background: var(--color-surface); }

  .tablePanel-toggle::-webkit-details-marker { display: none; }

  /* Disclosure triangle: a CSS shape, so it never enters the accessible
     name, sized up and coloured for a clear collapsed/open cue. */
  .tablePanel-toggle::before {
    content: "";
    flex: none;
    width: 0;
    height: 0;
    border-top: 0.45rem solid transparent;
    border-bottom: 0.45rem solid transparent;
    border-left: 0.6rem solid var(--color-text);
    transition: transform 120ms ease;
  }

  .tablePanel[open] > .tablePanel-toggle::before {
    transform: rotate(90deg);
  }

  @media (prefers-reduced-motion: reduce) {
    .tablePanel-toggle::before { transition: none; }
  }

  .tablePanel-title { font-size: 1.0625rem; margin: 0; }

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

  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-s);
    white-space: normal;
  }

  .badges-item {
    padding: 0.125rem var(--space-s);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-s);
    font-size: 0.8125rem;
    white-space: nowrap;
  }

  .trend {
    color: var(--color-up);
    font-weight: 700;
  }

  .trend--down { color: var(--color-down); }

  .linkIcon {
    display: inline-block;
    width: 12px;
    height: 12px;
    margin-right: var(--space-xs);
    vertical-align: -1px;
    background-size: contain;
    background-repeat: no-repeat;
  }

  .linkIcon--aa { background-image: url("__FAVICON_AA__"); }

  .linkIcon--ddg { background-image: url("__FAVICON_DDG__"); }

  .linkIcon--epoch { background-image: url("__FAVICON_EPOCH__"); }

  .linkIcon--opencode { background-image: url("__FAVICON_OPENCODE__"); }

  .linksCell {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-s);
  }

  .linksCell-link {
    display: inline-flex;
    align-items: center;
    white-space: nowrap;
  }

  .changesLog-marker { flex: none; width: 1em; color: var(--color-up); }

  .changesLog-marker--down { color: var(--color-down); }

  .changesSection-heading { margin-bottom: var(--space-m); }

  .visuallyHidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }

  .tableRow--tier1 { background: var(--color-tier1-bg); }
  .tableRow--tier2 { background: var(--color-tier2-bg); }
  .tableRow--tier3 { background: var(--color-tier3-bg); }
  .tableRow--tier4 { background: var(--color-tier4-bg); }
  .tableRow--tier5 { background: var(--color-tier5-bg); }

  /* Recency marks override tier tints when both apply. */
  /* Models with no Go or Go Plus allowance and no badge are outside the
     curated sets. 0.72 keeps text above WCAG AA on both backgrounds. */
  .tableRow--unavailable { opacity: 0.72; }

  .tableRow--new { background: var(--color-new-bg); }
  .tableRow--changed { background: var(--color-changed-bg); }

  .emptyState {
    padding: var(--space-m);
    border-top: 1px solid var(--color-border);
    color: var(--color-text-muted);
  }

  .changesLog-entry {
    margin-top: var(--space-m);
    padding-top: var(--space-m);
    border-top: 1px solid var(--color-border);
    scroll-margin-top: var(--space-m);
  }

  .changesLog-entry:first-child {
    margin-top: 0;
    padding-top: 0;
    border-top: 0;
  }

  .changesLog-entry:target { background: var(--color-surface); }

  .changesLog-entryTitle {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-s);
    font-size: 0.9375rem;
  }

  .changesLog-time { color: var(--color-text-muted); font-weight: 400; }

  .changesLog-permalink { font-weight: 400; }

  .changesLog-detail { margin-top: var(--space-s); }

  .changesLog-label {
    margin-top: var(--space-s);
    color: var(--color-text-muted);
    font-size: 0.8125rem;
  }

  .changesLog-items { margin-top: var(--space-xs); }
  .changesLog-items li + li { margin-top: var(--space-xs); }

  /* Two-column rows: the marker column is fixed, so wrapped lines always
     align under the text. */
  .changesLog-items li {
    display: flex;
    align-items: baseline;
    gap: var(--space-s);
  }

  .changesLog-text { flex: 1 1 auto; min-width: 0; }

  .changesLog-note { color: var(--color-text-muted); }

  .pageFooter {
    padding-top: var(--space-m);
    border-top: 1px solid var(--color-border);
    color: var(--color-text-muted);
    font-size: 0.875rem;
  }

}
"""

_STYLESHEET = (
    _STYLESHEET.replace("__FAVICON_AA__", _FAVICON_AA)
    .replace("__FAVICON_DDG__", _FAVICON_DDG)
    .replace("__FAVICON_EPOCH__", _FAVICON_EPOCH)
    .replace("__FAVICON_OPENCODE__", _FAVICON_OPENCODE)
)

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
  const goIndex = headers.findIndex(function (th) {
    const button = th.querySelector("button");
    return button !== null && button.textContent.trim() === "Go";
  });
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
        if (order !== 0) {
          return direction === "ascending" ? order : -order;
        }
        // Every column falls back to the Go column: ties order by the
        // most generous allowance first.
        if (goIndex < 0) { return 0; }
        const goLeft = sortValue(a.cells[goIndex], "num");
        const goRight = sortValue(b.cells[goIndex], "num");
        return goLeft < goRight ? 1 : goLeft > goRight ? -1 : 0;
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


def _allowance_tier(entry: ModelEntry) -> int:
    """Heat tier from the Go allowance: 1 (hottest) to 5, 0 for no listing.

    Unlimited allowances are the hottest tier; paid allowances tier at
    $100 / $50 / $20 thresholds, with every remaining paid tier at 5.
    """
    value = entry["go_allowance"]
    if value is None:
        return 0
    if "∞" in value:
        return 1
    amount = _allowance_float(value)
    if amount >= 100:
        return 2
    if amount >= 50:
        return 3
    if amount >= 20:
        return 4
    if amount >= 1:
        return 5
    return 0


def _tier_class(entry: ModelEntry) -> str:
    tier = _allowance_tier(entry)
    return f" tableRow--tier{tier}" if tier else ""


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


def _badges(entry: ModelEntry) -> str:
    badges = list(entry["badges"])
    if entry["is_free"] and "Free" not in badges:
        badges.append("Free")
    if not badges:
        return "—"
    spans = "".join(
        f'<span class="badges-item">{_esc(badge)}</span>' for badge in badges
    )
    return f'<span class="badges">{spans}</span>'


def _th(label: str, module: str, sort_type: str, *, default: str = "none") -> str:
    return (
        f'<th scope="col" aria-sort="{default}">'
        f'<button type="button" class="{module}-sort" '
        f'data-sort-type="{sort_type}">{_esc(label)}</button></th>'
    )


def _td(content: str, *, value: str | None = None) -> str:
    data = f' data-value="{_esc(value)}"' if value is not None else ""
    return f"<td{data}>{content}</td>"


def _model_heading_cell(entry: ModelEntry) -> str:
    name = _esc(entry["name"])
    if entry.get("opencode_url"):
        icon_variant, href = "opencode", entry["opencode_url"]
    elif entry.get("info_url"):
        icon_variant, href = "aa", entry["info_url"]
    else:
        icon_variant, href = "ddg", duckduckgo_ai_url(entry["name"])
    icon_tag = (
        f'<span class="linkIcon linkIcon--{icon_variant}" aria-hidden="true"></span>'
    )
    return f'<th scope="row">{icon_tag}<a href="{_esc(href)}">{name}</a></th>'


def _links_cell(entry: ModelEntry) -> str:
    """Destinations in a fixed order: DuckDuckGo, OpenCode, AA, then Epoch."""
    name = entry["name"]
    destinations = [
        (
            "ddg",
            duckduckgo_ai_url(name),
            "DDG",
            f"DuckDuckGo AI search for {name}",
        )
    ]
    if entry.get("opencode_url"):
        destinations.append(
            ("opencode", entry["opencode_url"], "OpenCode", f"OpenCode page for {name}")
        )
    if entry.get("info_url"):
        destinations.append(
            ("aa", entry["info_url"], "AA", f"Artificial Analysis page for {name}")
        )
    if entry.get("epoch_url"):
        destinations.append(
            ("epoch", entry["epoch_url"], "Epoch", f"Epoch AI page for {name}")
        )
    links = "".join(
        f'<a class="linksCell-link" href="{_esc(href)}" '
        f'aria-label="{_esc(aria)}">'
        f'<span class="linkIcon linkIcon--{variant}" aria-hidden="true"></span>'
        f'<span>{_esc(label)}</span></a>'
        for variant, href, label, aria in destinations
    )
    return f'<td class="linksCell">{links}</td>'


def _trend_cell(entry: ModelEntry) -> str:
    trend = entry.get("last_trend")
    if trend == "up":
        content = (
            '<span class="trend" aria-hidden="true">▲</span>'
            '<span class="visuallyHidden">better</span>'
        )
    elif trend == "down":
        content = (
            '<span class="trend trend--down" aria-hidden="true">▼</span>'
            '<span class="visuallyHidden">worse</span>'
        )
    else:
        content = "—"
    return _td(content, value=trend or "")


def _change_marker(direction: int) -> str:
    if direction > 0:
        return (
            '<span class="visuallyHidden">Better: </span>'
            '<span class="changesLog-marker" aria-hidden="true">▲</span>'
        )
    if direction < 0:
        return (
            '<span class="visuallyHidden">Worse: </span>'
            '<span class="changesLog-marker changesLog-marker--down" '
            'aria-hidden="true">▼</span>'
        )
    return '<span class="changesLog-marker" aria-hidden="true"></span>'


def _is_promo(entry: ModelEntry) -> bool:
    return bool(entry["badges"]) and not entry["is_free"]


def _in_curated_set(entry: ModelEntry) -> bool:
    """True when the Go console lists the model: an allowance or a badge."""
    return bool(
        entry["badges"]
        or entry["go_allowance"] is not None
        or entry["go_plus_allowance"] is not None
    )


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
    row_classes = "tableRow" + _tier_class(entry)
    if not _in_curated_set(entry):
        row_classes += " tableRow--unavailable"
    return (
        f'<tr class="{row_classes}">'
        f"{_trend_cell(entry)}"
        f"{_model_heading_cell(entry)}"
        f"{_links_cell(entry)}"
        f"{_td(go, value=go_value)}"
        f"{_td(go_plus, value=go_plus_value)}"
        f"{_td(_badges(entry), value=badges)}"
        f"{_td(in_cost, value=in_value)}"
        f"{_td(out_cost, value=out_value)}"
        f"{_td(since, value=since_value)}"
        f"</tr>"
    )


def _model_row(
    entry: ModelEntry,
    today: str,
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
    badges = list(dict.fromkeys(badges))  # dedupe, preserve order
    row_classes = (
        "tableRow"
        + _tier_class(entry)
        + (" tableRow--new" if "New" in flags else "")
        + (" tableRow--changed" if "Recently changed" in flags else "")
        + ("" if _in_curated_set(entry) else " tableRow--unavailable")
    )
    badge_spans = "".join(
        f'<span class="badges-item">{_esc(badge)}</span>' for badge in badges
    ) or "—"
    badge_block = (
        f'<span class="badges">{badge_spans}</span>'
        if badge_spans != "—"
        else badge_spans
    )
    return (
        f'<tr class="{row_classes}">'
        f"{_trend_cell(entry)}"
        f"{_model_heading_cell(entry)}"
        f"{_links_cell(entry)}"
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
        f'<tr>{_th("Trend", module, "text")}'
        f"{_th('Model', module, 'text')}"
        f"{_th('Links', module, 'text')}"
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
        f'<tr>{_th("Trend", "modelsTable", "text")}'
        f'{_th("Model", "modelsTable", "text")}'
        f'{_th("Links", "modelsTable", "text")}'
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
    rows = "".join(_model_row(entry, today, baseline_date) for entry in ordered)
    return (
        f'<div class="tableScroll" tabindex="0" role="region" '
        f'aria-labelledby="all-models-heading">'
        f'<table class="modelsTable">'
        f"<caption>All tracked models from models.dev and the Go console. "
        f"Trend shows the direction of the latest change: "
        f'<span class="trend" aria-hidden="true">▲</span> better, '
        f'<span class="trend trend--down" aria-hidden="true">▼</span> worse. '
        f"Rows are tinted in five tiers by Go monthly allowance: unlimited, "
        f"$100 and up, $50 and up, $20 and up, then lower paid tiers; models "
        f"with no Go listing are untinted. New and Recently changed mark "
        f"models from the last {RECENT_WINDOW_DAYS} days. Rows start sorted "
        f"by Go allowance, and sorting any column falls back to Go order "
        f"when values tie.</caption>"
        f"<thead>{head}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


def _panel(heading_id: str, title: str, inner: str) -> str:
    # Tables ship collapsed: no `open` attribute, so the page opens small.
    return (
        f'<details class="tablePanel">'
        f'<summary class="tablePanel-toggle">'
        f'<h2 class="tablePanel-title" id="{heading_id}">{_esc(title)}</h2>'
        f"</summary>"
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


def _model_label(
    names: dict[str, str], models: dict[str, ModelEntry], key: str
) -> str:
    current = models.get(key)
    return names.get(key) or (current["name"] if current else key)


def _changes_log(
    history: list[HistoryEntry], models: dict[str, ModelEntry]
) -> str:
    if not history:
        return '<p class="emptyState">No changes recorded yet.</p>'
    items: list[str] = []
    for entry in reversed(history):
        anchor = entry_anchor(entry["id"])
        names = entry.get("names") or {}

        def label(key: str, entry_names: dict[str, str] = names) -> str:
            return _model_label(entry_names, models, key)

        details: list[str] = []
        if entry.get("note"):
            details.append(f'<p class="changesLog-note">{_esc(entry["note"])}</p>')
        if entry["added"]:
            starting = "".join(
                f'<li>{_change_marker(1)}'
                f'<span class="changesLog-text">{_esc(label(key))}</span></li>'
                for key in entry["added"]
            )
            details.append(
                f'<p class="changesLog-label">Starting</p>'
                f'<ul class="changesLog-items">{starting}</ul>'
            )
        if entry["changed"]:
            changed_items = ""
            for change in entry["changed"]:
                direction = change_direction(
                    change["field"], change["old"], change["new"]
                )
                changed_items += (
                    f'<li>{_change_marker(direction)}'
                    f'<span class="changesLog-text">'
                    f"<strong>{_esc(label(change['key']))}</strong>: "
                    f"{_esc(field_label(change['field']))} from "
                    f"{_esc(format_value(change['field'], change['old']))} to "
                    f"{_esc(format_value(change['field'], change['new']))}"
                    f"</span></li>"
                )
            details.append(
                f'<p class="changesLog-label">Changed</p>'
                f'<ul class="changesLog-items">{changed_items}</ul>'
            )
        if entry["removed"]:
            ended = "".join(
                f'<li>{_change_marker(-1)}'
                f'<span class="changesLog-text">{_esc(label(key))}</span></li>'
                for key in entry["removed"]
            )
            details.append(
                f'<p class="changesLog-label">Ended</p>'
                f'<ul class="changesLog-items">{ended}</ul>'
            )
        if entry["degraded"]:
            details.append(
                '<p class="changesLog-note">Go and Go Plus allowances could not '
                "be refreshed in this run. The figures were carried forward from "
                "the last successful check.</p>"
            )
        if not details:
            continue
        timestamp = entry["timestamp"]
        items.append(
            f'<li class="changesLog-entry" id="{_esc(anchor)}">'
            f'<h3 class="changesLog-entryTitle">'
            f'<span class="changesLog-title">{_esc(entry["title"])}</span>'
            f'<time class="changesLog-time" datetime="{_esc(timestamp)}">'
            f"{_esc(format_timestamp(timestamp))}</time>"
            f'<a class="changesLog-permalink" href="#{_esc(anchor)}" '
            f'aria-label="Link to this entry">#</a>'
            f"</h3>"
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
    updated_human = format_timestamp(updated)
    today = updated.split("T")[0]
    baseline_date = history[0]["timestamp"].split("T")[0] if history else None
    promos = _deal_table(
        promo_entries,
        "promos-heading",
        "dealsTable",
        "Models with an active promotion, tinted by Go allowance tier. "
        "Trend: ▲ better, ▼ worse.",
        "No active promotions right now.",
    )
    frees = _deal_table(
        free_entries,
        "free-heading",
        "freeTable",
        "Models with a free tier, tinted by Go allowance tier. "
        "Trend: ▲ better, ▼ worse.",
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
<p class="pageHeader-meta">Last updated
<time datetime="{_esc(updated)}">{_esc(updated_human)}</time></p>
<p class="pageHeader-meta">Subscribe: <a href="feed.xml">Atom feed</a></p>
</header>
<main id="main-content">
{_banner(snapshot)}
{_panel("promos-heading", "Promos", promos)}
{_panel("free-heading", "Free models", frees)}
{_panel("all-models-heading", "All tracked models", all_models)}
<section aria-labelledby="changes-heading">
<h2 class="changesSection-heading" id="changes-heading">Recent changes</h2>
{_changes_log(history, models)}
</section>
</main>
<footer class="pageFooter">
<p>Data: <a href="deals.json">deals.json</a>
&middot; sources: models.dev and the OpenCode Go console.</p>
<p>Model names link to the OpenCode model page, or to Artificial
Analysis or a DuckDuckGo AI search where no page exists. The Links
column lists DuckDuckGo, OpenCode, Artificial Analysis and Epoch AI
destinations where they exist.</p>
</footer>
</div>
<script>{_SCRIPT}</script>
</body>
</html>
"""
