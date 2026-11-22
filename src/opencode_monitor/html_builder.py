"""Self-contained, accessible static HTML page generation.

Design notes:
- Single file, inline ``<style>`` only: no JavaScript, web fonts, or external
  requests of any kind.
- MaintainableCSS: semantic lowerCamelCase module classes
  (``.module-component``), flat single-class selectors, ``@media`` co-located
  with the owning module.
- Cascade layers: ``reset, tokens, base, layout, components``.
- WCAG 2.2 AA: skip link, landmarks, table captions, ``th scope``, scrollable
  regions with ``role="region"``, ``<time>`` stamps, text labels for badges
  (never colour alone), and contrast-checked light/dark tokens.
"""

from __future__ import annotations

import html
from typing import Any

from .config import Settings
from .models import HistoryEntry, ModelEntry, Snapshot

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
    --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
    }
  }
}

@layer base {
  body {
    font-family: var(--font-sans);
    font-size: 1rem;
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
    max-width: 64rem;
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

  .tableScroll {
    overflow-x: auto;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-s);
  }

  .dealsTable, .modelsTable { width: 100%; }

  .dealsTable caption, .modelsTable caption {
    padding: var(--space-m);
    text-align: left;
    color: var(--color-text-muted);
  }

  .dealsTable th, .dealsTable td, .modelsTable th, .modelsTable td {
    padding: var(--space-s) var(--space-m);
    border-bottom: 1px solid var(--color-border);
    text-align: left;
    vertical-align: top;
  }

  .dealsTable thead th, .modelsTable thead th {
    background: var(--color-surface);
  }

  .dealsTable-badges, .modelsTable-badges {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-s);
  }

  .dealsTable-badge, .modelsTable-badge {
    padding: 0.125rem var(--space-s);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-s);
    font-size: 0.875rem;
    white-space: nowrap;
  }

  .dealsTable-num, .modelsTable-num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .emptyState {
    padding: var(--space-m);
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


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fmt_cost(value: float | None) -> str:
    return "—" if value is None else f"${value:.2f}"


def _fmt_int(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def _fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    return f'<time datetime="{_esc(value)}">{_esc(value)}</time>'


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


def _is_promo(entry: ModelEntry) -> bool:
    return bool(entry["badges"]) or entry["is_free"]


def _table(rows: str, caption: str, table_id: str, module: str) -> str:
    return (
        f'<div class="tableScroll" tabindex="0" role="region" '
        f'aria-labelledby="{table_id}">'
        f'<table class="{module}Table">'
        f"<caption>{caption}</caption>"
        f"<thead><tr>"
        f'<th scope="col">Model</th>'
        f'<th scope="col">Go</th>'
        f'<th scope="col">Go Plus</th>'
        f'<th scope="col">Badges</th>'
        f'<th scope="col">In $/M</th>'
        f'<th scope="col">Out $/M</th>'
        f'<th scope="col">Active since</th>'
        f"</tr></thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


def _promo_row(entry: ModelEntry) -> str:
    return (
        f'<tr><th scope="row">{_esc(entry["name"])}</th>'
        f'<td class="dealsTable-num">{_esc(entry["go_allowance"] or "—")}</td>'
        f'<td class="dealsTable-num">{_esc(entry["go_plus_allowance"] or "—")}</td>'
        f"<td>{_badges(entry, 'dealsTable')}</td>"
        f'<td class="dealsTable-num">{_fmt_cost(entry["input_cost_per_m"])}</td>'
        f'<td class="dealsTable-num">{_fmt_cost(entry["output_cost_per_m"])}</td>'
        f"<td>{_fmt_date(entry['allowance_since'])}</td></tr>"
    )


def _model_row(entry: ModelEntry) -> str:
    return (
        f'<tr><th scope="row">{_esc(entry["name"])}</th>'
        f'<td class="modelsTable-num">{_esc(entry["id"])}</td>'
        f'<td class="modelsTable-num">{_esc(", ".join(entry["providers"]) or "—")}</td>'
        f'<td class="modelsTable-num">{_fmt_int(entry["context_limit"])}</td>'
        f'<td class="modelsTable-num">{_fmt_int(entry["output_limit"])}</td>'
        f'<td class="modelsTable-num">{_fmt_cost(entry["input_cost_per_m"])}</td>'
        f'<td class="modelsTable-num">{_fmt_cost(entry["output_cost_per_m"])}</td>'
        f'<td class="modelsTable-num">{_esc(entry["go_allowance"] or "—")}</td>'
        f'<td class="modelsTable-num">{_esc(entry["go_plus_allowance"] or "—")}</td>'
        f"<td>{_badges(entry, 'modelsTable')}</td>"
        f"<td>{_fmt_date(entry['first_seen'])}</td></tr>"
    )


def _all_models_table(rows: str) -> str:
    return (
        f'<div class="tableScroll" tabindex="0" role="region" '
        f'aria-labelledby="all-models-heading">'
        f'<table class="modelsTable">'
        f"<caption>All tracked models from models.dev and the Go console</caption>"
        f"<thead><tr>"
        f'<th scope="col">Model</th>'
        f'<th scope="col">ID</th>'
        f'<th scope="col">Providers</th>'
        f'<th scope="col">Context</th>'
        f'<th scope="col">Output cap</th>'
        f'<th scope="col">In $/M</th>'
        f'<th scope="col">Out $/M</th>'
        f'<th scope="col">Go</th>'
        f'<th scope="col">Go Plus</th>'
        f'<th scope="col">Badges</th>'
        f'<th scope="col">First seen</th>'
        f"</tr></thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
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
            f'<h3 class="changesLog-entryTitle">{_esc(entry["title"])} '
            f'— <time datetime="{_esc(timestamp)}">{_esc(timestamp)}</time></h3>'
            f'<div class="changesLog-detail">{"".join(details)}</div>'
            f"</li>"
        )
    if not items:
        return '<p class="emptyState">No changes recorded yet.</p>'
    return f'<ol class="changesLog">{"".join(items)}</ol>'


def build_page(snapshot: Snapshot, history: list[HistoryEntry], settings: Settings) -> str:
    """Render the full self-contained status page."""
    models = snapshot["models"]
    promo_rows = "".join(_promo_row(entry) for entry in models.values() if _is_promo(entry))
    promo_section = (
        _table(
            promo_rows,
            "Models with an active promotion or free tier",
            "promos-heading",
            "deals",
        )
        if promo_rows
        else '<p class="emptyState">No active promotions or free models right now.</p>'
    )

    model_rows = "".join(_model_row(entry) for entry in models.values())
    updated = snapshot["updated_at"]

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
<section aria-labelledby="promos-heading">
<h2 id="promos-heading">Promos and free models</h2>
{promo_section}
</section>
<section aria-labelledby="all-models-heading">
<h2 id="all-models-heading">All tracked models</h2>
{_all_models_table(model_rows)}
</section>
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
</body>
</html>
"""
