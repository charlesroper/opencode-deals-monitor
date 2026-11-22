# OpenCode Go Deals Monitor

A small Python CLI that checks OpenCode Go model deals every day and publishes
what changed. It runs on GitHub Actions in a public repository, needs no
secrets, and costs nothing to operate.

The monitor reads two live sources:

- `models.dev/api.json` for model IDs, context and output limits, per-token
  prices, and free tiers under the `opencode-go` and `opencode` providers.
- The OpenCode Go console page for monthly Go and Go Plus dollar allowances
  and promotional badges such as `New` or `Limited time`.

When a deal starts, changes or ends, the run writes three files and deploys
them to GitHub Pages:

- `feed.xml`, an Atom 1.0 feed for feed readers and RSS-to-email services.
- `index.html`, a static status page in a monospace design. Promos, free
  models and the full model list each sit in a collapsed panel, and every
  table opens sorted by Go allowance, largest first; sorting any column
  falls back to Go order when values tie. Rows are tinted in five tiers by
  Go allowance: unlimited, $100 and up, $50 and up, $20 and up, then lower
  paid tiers. New marks models that arrived after monitoring began, and
  Recently changed marks models updated in the last 7 days. Click any
  column to re-sort. Recent changes lists each deal event newest first;
  every entry has a permalink, and each Atom entry links straight to its
  changelog entry. A few lines of inline JavaScript handle sorting, and
  the page loads no external scripts, fonts or other assets.
- `deals.json`, a JSON snapshot for scripts and dashboards.

Quiet days write nothing and exit with code `0`, so the live site stays as it
was until something changes.

## Data sources and how they are joined

Entries from both sources are joined on a normalised key: the model name or ID
lowercased with punctuation and spaces removed, so `GLM-5.3-Flash` and
`glm-5.3-flash` both become `glm53flash`. A model that appears in only one
source is kept, never dropped.

The console page is server-rendered, so the parser reads the static DOM with
BeautifulSoup (`html.parser`, no JavaScript execution):

- Rows: `tr[data-model]`.
- Display names: `span[data-layer="model-name"]`.
- Allowances: the `td[data-allowance-type="usage"]` cell, where the layered
  `span[data-plan="go"]` and `span[data-plan="go-plus"]` values carry the
  dollar figures.
- Badges: `span.console-go-models-new` and `span.console-go-models-note`
  (the note text is split on `·`).

The page was inspected for hydration payloads before this strategy was
chosen. The models table ships complete in the static HTML, so DOM parsing is
used directly and no embedded JSON bootstrap needs decoding.

The two sources are treated as unequal partners:

- If `models.dev/api.json` fails after two retries, the run stops with exit
  code `1` and writes nothing.
- If the console scrape fails, parses zero models, or drops by more than half
  against the previous snapshot, the run degrades: the previous allowances,
  badges and verification timestamp are carried forward, the status page
  shows a stale-data notice, and the run exits with code `2`. A degraded run
  still publishes any models.dev changes.

## Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Clean run: quiet day, update published, or first run. |
| `1` | Fatal: `models.dev/api.json` could not be fetched or parsed. Nothing written. |
| `2` | Partial degradation: console scrape failed or dropped. Prior allowances carried forward; run still published. |

## Set up the repository

1. Create a public GitHub repository and push this code to `main`.
2. In the repository, open **Settings**, then **Pages**. Under **Build and
   deployment**, set **Source** to **GitHub Actions**.
3. In your GitHub account, open **Settings**, then **Notifications**, then
   **Actions**. Enable email notifications for failed workflow runs, so exit
   codes `1` and `2` reach you automatically.
4. Open **Actions**, select **Monitor**, then **Run workflow** for the first
   run. This seeds `data/state.json` and `data/history.json` and deploys the
   initial site.
5. Add `https://<owner>.github.io/<repo>/feed.xml` to your feed reader, or
   read `https://<owner>.github.io/<repo>/deals.json` from your scripts.

The scheduled run executes daily at 08:23 UTC, off the top of the hour to
reduce cron jitter. GitHub disables scheduled workflows after 60 days without
repository activity, so the workflow pushes an empty keepalive commit when the
last commit on `main` is older than 45 days.

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

- `--dry-run`: fetch and print the computed diff without writing files.
- `--force`: rebuild `public/feed.xml`, `public/index.html` and
  `public/deals.json` even when nothing changed.
- `--json-fixture=<path>`: read the models.dev payload from a local file
  instead of the network.
- `--html-fixture=<path>`: read the console page from a local file instead of
  the network.

The repository pins Python 3.14 in `.python-version`; `uv` installs it
automatically.

## Configuration

All settings have sensible defaults and can be overridden with environment
variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MODELS_API_URL` | `https://models.dev/api.json` | Structured models JSON endpoint |
| `CONSOLE_GO_URL` | `https://opencode.ai/console/go` | OpenCode Go console page |
| `PUBLIC_BASE_URL` | `https://<owner>.github.io/<repo>` | Base URL for Atom links and ids |
| `FEED_TITLE` | `OpenCode Go Deals Monitor` | Page and feed title |
| `HISTORY_LIMIT` | `30` | Entries kept in `data/history.json` and `feed.xml` |
| `DATA_DIR` | `data` | Directory for `state.json` and `history.json` |
| `PUBLIC_DIR` | `public` | Directory for `index.html`, `feed.xml`, `deals.json` |

## Troubleshooting

- If the job fails with exit code `1`, `models.dev/api.json` was unreachable
  or invalid. Check the URL and try a manual run.
- If the job fails with exit code `2`, the console scrape degraded. Open
  `https://opencode.ai/console/go` in a browser to check whether the page
  structure changed; the run carries the previous allowances forward until a
  healthy scrape recovers.
- If the feed shows nothing new, the day was quiet: no diff, no writes. Run
  the workflow manually with the `force` input to rebuild the page.
- If GitHub Pages does not update, check that `public/index.html` was built
  in the failing run. The deploy step only runs when that file exists.
