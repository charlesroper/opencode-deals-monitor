# OpenCode Go Deals Monitor

[![Monitor](https://img.shields.io/github/actions/workflow/status/charlesroper/opencode-deals-monitor/monitor.yml?label=monitor)](https://github.com/charlesroper/opencode-deals-monitor/actions/workflows/monitor.yml)
[![CI](https://img.shields.io/github/actions/workflow/status/charlesroper/opencode-deals-monitor/ci.yml?label=ci)](https://github.com/charlesroper/opencode-deals-monitor/actions/workflows/ci.yml)
[![Site](https://img.shields.io/website?url=https%3A%2F%2Fcharlesroper.github.io%2Fopencode-deals-monitor%2F&label=site)](https://charlesroper.github.io/opencode-deals-monitor/)
[![Python](https://img.shields.io/badge/python-3.14-blue)](https://www.python.org/)
[![Licence](https://img.shields.io/github/license/charlesroper/opencode-deals-monitor)](https://github.com/charlesroper/opencode-deals-monitor/blob/main/LICENSE)
[![Feed](https://img.shields.io/badge/feed-Atom-orange)](https://charlesroper.github.io/opencode-deals-monitor/feed.xml)
[![Runtime deps](https://img.shields.io/badge/runtime_deps-2-brightgreen)](https://github.com/charlesroper/opencode-deals-monitor/blob/main/pyproject.toml)

**Live site:** https://charlesroper.github.io/opencode-deals-monitor/

A daily Python CLI that checks OpenCode Go model deals and publishes what
changed. It runs on GitHub Actions in a public repository, needs no secrets,
and costs nothing to run.

Two live sources feed it: models.dev for model data and prices, and the
OpenCode Go console for monthly allowances and promotional badges.

## What gets published

Each publishing run writes three files and deploys them to GitHub Pages:

- **`feed.xml`** is an Atom 1.0 feed for readers and RSS-to-email services.
- **`index.html`** is a static status page, described below.
- **`deals.json`** is a JSON snapshot for scripts and dashboards.

Quiet days write nothing and exit `0`, so the live site stays untouched.

## How it works

The run happens on GitHub Actions, on a GitHub-hosted Ubuntu runner, inside
this public repository. A cron schedule starts it at 08:23 UTC each day. The
**Actions** tab, then **Monitor**, then **Run workflow** starts it by hand,
with an optional `force` input that rebuilds the site even when nothing
changed.

The runner installs Python 3.14 with `uv` and runs the `opencode-monitor`
command. One run follows six steps:

1. **Fetch.** Get `models.dev/api.json` and the Go console page. Both requests retry transient failures twice.
2. **Parse.** Read the JSON directly. Read the console table with BeautifulSoup; the table ships complete in the HTML.
3. **Merge.** Join on a normalised key, keep models found in one source only, and carry forward allowances and badges when the console scrape degrades.
4. **Diff.** Compare with the last snapshot. Sort the result into models that started, changed or ended, and stamp each change with its date and trend.
5. **Publish.** Stop on a quiet day and write nothing. Otherwise write state and history, verify model links, then write the Atom feed, the status page and the JSON snapshot.
6. **Deploy.** The workflow commits state changes, uploads the site, and deploys it from a second job. A failure sends the GitHub email.

## The status page

The page uses a monospace design and system fonts. It loads no external
assets and needs a few lines of inline JavaScript for sorting.

- **Panels.** Promos, Free models and All tracked models start collapsed.
- **Sorting.** Every table opens sorted by Go allowance, largest first. Click
  any column to re-sort; ties fall back to Go order.
- **Trend.** `▲` marks a change in your favour and `▼` one against. The Trend
  column and each changelog item carry the same marker.
- **Links.** Each model name is followed by a Links column: DuckDuckGo AI
  search first, then the OpenCode model page, Artificial Analysis and Epoch
  AI pages where they exist. Model names link to the OpenCode page when
  there is one.
- **Heat tiers.** Rows are tinted in five tiers by Go allowance: unlimited,
  $100 and up, $50 and up, $20 and up, then lower paid tiers.
- **New and Recently changed.** Models that arrived after monitoring began,
  or changed in the last 7 days, are flagged. The starting inventory is
  never flagged New.
- **Recent changes.** Every deal event, newest first, each with a permalink.
  Atom entries link straight to their changelog entry.

## Data sources

- **`models.dev/api.json`**: model IDs, context and output limits, per-token
  prices, and free tiers under the `opencode-go` and `opencode` providers.
- **`opencode.ai/console/go`**: monthly Go and Go Plus allowances, plus
  badges such as `New` or `Limited time`.

Entries join on a normalised key: the name or ID lowercased, with punctuation
and spaces removed. `GLM-5.3-Flash` and `glm-5.3-flash` both become
`glm53flash`. A model found in only one source is kept.

The console page is server-rendered, so the parser reads the static DOM:

- Rows: `tr[data-model]`.
- Names: `span[data-layer="model-name"]`.
- Allowances: `td[data-allowance-type="usage"]`, reading its `data-plan`
  spans.
- Badges: `span.console-go-models-new` and `span.console-go-models-note`.

The table ships complete in the HTML, so no hydration payload is parsed.

Fault tolerance differs by source:

- If `models.dev` fails after two retries, the run stops with exit `1` and
  writes nothing.
- If the console scrape fails, parses zero models, or drops by more than
  half, the run carries forward the previous allowances and badges. It shows
  a stale-data notice, publishes what it has, and exits `2`.

## Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Clean run: quiet day, update published, or first run. |
| `1` | Fatal: `models.dev/api.json` could not be fetched or parsed. Nothing written. |
| `2` | Partial degradation: the console scrape failed or dropped by more than half. Previous allowances carried forward; run still published. |

## Set up the repository

1. Create a public GitHub repository and push this code to `main`.
2. In **Settings**, then **Pages**, set **Source** to **GitHub Actions**.
3. In your account's **Settings**, then **Notifications**, then **Actions**,
   turn on email alerts for failed workflow runs.
4. In **Actions**, pick **Monitor**, then **Run workflow** for the first run.
   It seeds `data/state.json` and `data/history.json` and deploys the site.
5. Add `https://<owner>.github.io/<repo>/feed.xml` to your feed reader, or
   read `https://<owner>.github.io/<repo>/deals.json` from your scripts.

The schedule runs daily at 08:23 UTC, off the hour to reduce cron jitter.
GitHub disables schedules after 60 days without repository activity, so the
workflow pushes a keepalive commit once `main` is 45 days idle.

## Run it yourself

1. Install [uv](https://docs.astral.sh/uv/).
2. Sync the environment:

   ```bash
   uv sync
   ```

3. Try a run without writing anything:

   ```bash
   uv run opencode-monitor --dry-run
   ```

4. Lint and test:

   ```bash
   uv run ruff check .
   uv run pytest
   ```

Flags:

- `--dry-run`: print the computed diff without writing files.
- `--force`: rebuild the public outputs even when nothing changed.
- `--json-fixture=<path>`: read the models.dev payload from a local file.
- `--html-fixture=<path>`: read the console page from a local file.
- `--no-link-check`: skip the link check against the review sites.

The first publishing run checks every model against OpenCode, Artificial
Analysis and Epoch AI, which adds about two minutes. Later runs check only
new models, and misses are rechecked monthly.

The repository pins Python 3.14 in `.python-version`; `uv` installs it.

## Configuration

All settings have defaults and can be overridden with environment variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MODELS_API_URL` | `https://models.dev/api.json` | Structured models JSON endpoint |
| `CONSOLE_GO_URL` | `https://opencode.ai/console/go` | OpenCode Go console page |
| `PUBLIC_BASE_URL` | `https://<owner>.github.io/<repo>` | Base URL for Atom links and ids |
| `FEED_TITLE` | `OpenCode Go Deals Monitor` | Page and feed title |
| `HISTORY_LIMIT` | `30` | Entries kept in `data/history.json` and `feed.xml` |
| `DATA_DIR` | `data` | Directory for `state.json` and `history.json` |
| `PUBLIC_DIR` | `public` | Directory for the published files |

## Dependencies

The monitor has two runtime dependencies. Everything else comes from the
Python standard library. Exact versions are pinned in `uv.lock`.

| Package | Role |
| :--- | :--- |
| `httpx` | HTTP client for both source fetches and the link checks |
| `beautifulsoup4` | HTML parser for the Go console table |

`httpx` was chosen over `requests` for three reasons:

- Separate connect and total timeouts, so a slow server cannot hang a run.
- `httpx.MockTransport`, which lets the tests run with no network.
- One client type for sync and async code, though the monitor uses only sync.

The link check reuses one client for all HEAD requests, so connections stay
open. The first full sweep takes about 30 seconds this way. A new connection
for each request took over three minutes.

Those two packages bring their own short chain: `httpcore` and `h11` for
transport, `anyio` for the async backend, `certifi` for CA certificates,
`idna` for hostnames, `soupsieve` for CSS selectors and `typing-extensions`.

Development tools:

| Package | Role |
| :--- | :--- |
| `pytest` | Test runner |
| `ruff` | Linter and formatter |
| `hatchling` | Build backend. Creates the package and the `opencode-monitor` command |

The standard library covers the rest:

- **Atom feed:** `xml.etree.ElementTree`.
- **JSON and atomic writes:** `json`, `os.replace` and `pathlib`.
- **Changelog ids:** `hashlib`.
- **HTML escaping:** `html`.
- **Search prompts:** `urllib.parse`.
- **CLI:** `argparse`.

The project does not use a web framework, a template engine, a feed library
or a test double library. The tests use `httpx.MockTransport` instead.

## Troubleshooting

- **The job fails with exit code 1.** `models.dev/api.json` was unreachable
  or invalid. Check the URL, then rerun the workflow.
- **The job fails with exit code 2.** The console scrape degraded. Open
  `https://opencode.ai/console/go` in a browser to check the page structure.
  The previous allowances stay live until a healthy scrape.
- **The feed shows nothing new.** The day was quiet: no diff, no writes. Run
  the workflow manually with the `force` input to rebuild the page.
- **GitHub Pages does not update.** Check whether the failing run built
  `public/index.html`. The deploy job only runs when that file exists.

## Licence

The code is released under the MIT licence. The destination icons for
OpenCode, DuckDuckGo, Artificial Analysis and Epoch AI remain the trademarks
of their owners. They appear only as link markers.
