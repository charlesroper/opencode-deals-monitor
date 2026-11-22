"""Builder and CLI tests: Atom feed, HTML page, JSON export, and run flow."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencode_monitor.atom_builder import ATOM_NS, build_feed, entry_id
from opencode_monitor.cli import main
from opencode_monitor.config import Settings
from opencode_monitor.html_builder import build_page
from opencode_monitor.models import HistoryEntry, ModelEntry, Snapshot

FIXTURES = Path(__file__).parent / "fixtures"
ATOM = f"{{{ATOM_NS}}}"

JSON_FIXTURE = str(FIXTURES / "models.dev.json")
HTML_FIXTURE = str(FIXTURES / "console-go.html")


@pytest.fixture(autouse=True)
def _no_link_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI tests offline: link checks answer "not covered" by default."""
    monkeypatch.setattr("opencode_monitor.cli.url_exists", lambda url, **_: False)


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "DATA_DIR": str(tmp_path / "data"),
            "PUBLIC_DIR": str(tmp_path / "public"),
            "PUBLIC_BASE_URL": "https://owner.github.io/opencode-deals-monitor",
        }
    )


def _entry(**overrides) -> ModelEntry:
    base = ModelEntry(
        key="alpha",
        id="alpha",
        name="Alpha",
        canonical_model_id=None,
        providers=["opencode-go"],
        context_limit=1000,
        output_limit=100,
        input_cost_per_m=1.0,
        output_cost_per_m=2.0,
        go_allowance="$60",
        go_plus_allowance="$120",
        badges=["New"],
        is_free=False,
        first_seen="2026-11-01",
        allowance_since="2026-11-01",
        last_changed="2026-11-01",
        last_trend=None,
        info_url=None,
        info_checked=None,
        epoch_url=None,
        epoch_checked=None,
        opencode_url=None,
        opencode_checked=None,
    )
    base.update(overrides)  # type: ignore[union-attr]
    return base


def _snapshot(**models: ModelEntry) -> Snapshot:
    return Snapshot(
        updated_at="2026-11-23T08:23:00Z",
        console_html_verified_at="2026-11-23T08:23:00Z",
        console_html_degraded=False,
        models=dict(sorted(models.items())),
    )


def _history(**overrides) -> HistoryEntry:
    base = HistoryEntry(
        id="urn:opencode-deals:2026-11-23:abc123",
        timestamp="2026-11-23T08:23:00Z",
        title="1 model started",
        added=["alpha"],
        changed=[],
        removed=[],
        degraded=False,
        note="",
        names={},
    )
    base.update(overrides)  # type: ignore[union-attr]
    return base


# --- Atom feed -----------------------------------------------------------


def test_feed_is_valid_atom() -> None:
    feed_xml = build_feed([_history()], _settings(Path("/tmp/opencode/test-tmp")))
    root = ET.fromstring(feed_xml)
    assert root.tag == f"{ATOM}feed"
    assert root.findtext(f"{ATOM}title") == "OpenCode Go Deals Monitor"
    assert root.find(f"{ATOM}link[@rel='self']") is not None
    assert root.find(f"{ATOM}link[@rel='alternate']") is not None
    entry = root.find(f"{ATOM}entry")
    assert entry is not None
    assert entry.findtext(f"{ATOM}id") == "urn:opencode-deals:2026-11-23:abc123"
    assert entry.findtext(f"{ATOM}updated") == "2026-11-23T08:23:00Z"
    feed_link = entry.find(f"{ATOM}link[@rel='alternate']")
    assert feed_link is not None
    assert feed_link.get("href", "").endswith("/#chg-2026-11-23-abc123")
    content = entry.find(f"{ATOM}content")
    assert content is not None
    assert content.get("type") == "html"
    assert "Starting" in (content.text or "")


def test_feed_limits_entries_to_history_limit() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp2"))
    settings = Settings(
        models_api_url=settings.models_api_url,
        console_go_url=settings.console_go_url,
        public_base_url=settings.public_base_url,
        feed_title=settings.feed_title,
        history_limit=3,
        data_dir=settings.data_dir,
        public_dir=settings.public_dir,
    )
    entries = [
        _history(id=f"urn:{i}", timestamp=f"2026-11-2{i % 10}T08:23:00Z", title=f"e{i}")
        for i in range(10)
    ]
    root = ET.fromstring(build_feed(entries, settings))
    assert len(root.findall(f"{ATOM}entry")) == 3


def test_entry_id_deterministic_per_day_and_content() -> None:
    a = entry_id("2026-11-23T08:23:00Z", ["x"], [], [])
    b = entry_id("2026-11-23T19:00:00Z", ["x"], [], [])
    c = entry_id("2026-11-23T08:23:00Z", ["y"], [], [])
    assert a == b
    assert a != c


def test_feed_content_escapes_model_names() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp3"))
    evil = _history(added=["<script>&boom"])
    feed_xml = build_feed([evil], settings)
    assert "<script>" not in feed_xml
    root = ET.fromstring(feed_xml)
    content = root.find(f"{ATOM}entry/{ATOM}content")
    assert content is not None
    # The content is HTML embedded in XML: parsed once it must hold the
    # html-escaped text, so a reader renders it as inert text.
    assert "&lt;script&gt;&amp;boom" in (content.text or "")


# --- HTML page -----------------------------------------------------------


def test_page_structure_and_accessibility() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp4"))
    page = build_page(_snapshot(alpha=_entry()), [_history()], settings)
    assert '<link rel="alternate" type="application/atom+xml"' in page
    assert '<a class="skipLink" href="#main-content">Skip to main content</a>' in page
    assert '<main id="main-content">' in page
    assert 'role="status"' not in page  # not degraded
    assert "<caption>" in page
    assert '<th scope="col" aria-sort="none">' in page
    assert '<th scope="row">' in page
    assert ">Alpha</a></th>" in page
    assert '<time datetime="2026-11-23T08:23:00Z">' in page
    assert 'tabindex="0" role="region"' in page
    assert "Last updated" in page
    # MaintainableCSS layers and tokens, monospace design.
    assert "@layer reset, tokens, base, layout, components;" in page
    assert "--color-text-muted" in page
    assert "prefers-color-scheme: dark" in page
    assert "--font-mono" in page
    assert "tabular-nums" in page


def test_tables_are_collapsible_and_closed() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp9"))
    page = build_page(_snapshot(alpha=_entry()), [], settings)
    assert page.count("<details") == 3  # promos, free, all models
    assert page.count("<summary") == 3
    assert "<details open" not in page  # collapsed by default
    assert '<details class="tablePanel">' in page
    assert '<summary class="tablePanel-toggle">' in page
    assert '<h2 class="tablePanel-title" id="promos-heading">Promos</h2>' in page
    assert '<h2 class="tablePanel-title" id="free-heading">Free models</h2>' in page
    assert '<h2 class="tablePanel-title" id="all-models-heading">All tracked models</h2>' in page


def test_every_column_is_sortable() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp10"))
    page = build_page(_snapshot(alpha=_entry()), [], settings)
    soup = BeautifulSoup(page, "html.parser")
    tables = soup.find_all("table")
    assert tables, "page should render tables"
    for table in tables:
        headers = table.thead.find_all("th")
        assert headers
        for th in headers:
            assert th.get("aria-sort") is not None
            button = th.find("button")
            assert button is not None, "every column needs a sort button"
            assert button.get("data-sort-type") in {"text", "num"}
            assert button.get("type") == "button"


def test_promos_and_free_models_are_separate() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp11"))
    snapshot = _snapshot(
        alpha=_entry(badges=["New"]),  # promo only
        beta=_entry(key="beta", id="beta", name="Beta", is_free=True),  # free only
        gamma=_entry(
            key="gamma", id="gamma", name="Gamma", is_free=True,
            badges=["Limited time"], go_allowance="$120",
        ),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    promos = soup.select_one("#promos-heading").find_parent("details")
    frees = soup.select_one("#free-heading").find_parent("details")
    promo_names = [th.get_text() for th in promos.select(".dealsTable tbody th")]
    free_names = [th.get_text() for th in frees.select(".freeTable tbody th")]
    assert promo_names == ["Alpha"]  # free models never appear in promos
    # Deal tables default to the most generous Go allowance first.
    assert free_names == ["Gamma", "Beta"]


def test_models_table_has_last_changed_column() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp12"))
    page = build_page(_snapshot(alpha=_entry(last_changed="2026-11-20")), [], settings)
    assert "Last changed" in page
    assert '<time datetime="2026-11-20">2026-11-20</time>' in page


def test_sort_values_are_machine_readable() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp13"))
    page = build_page(_snapshot(alpha=_entry()), [], settings)
    soup = BeautifulSoup(page, "html.parser")
    row = soup.select_one(".modelsTable tbody tr")
    cells = row.find_all("td")
    # Column order matches the deal tables, then the models-only columns.
    assert cells[0]["data-value"] == ""  # trend: no recorded change
    assert cells[1].get("class") == ["linksCell"]  # links: no sort value
    assert cells[2]["data-value"] == "60"  # Go: $60
    assert cells[3]["data-value"] == "120"  # Go Plus: $120
    assert cells[4]["data-value"] == "New"  # badges sort as text
    assert cells[5]["data-value"] == "1.0"  # In $/M
    assert cells[6]["data-value"] == "2.0"  # Out $/M
    assert cells[7].get("data-value") is None  # ID: plain text
    assert cells[8]["data-value"] == "opencode-go"  # providers
    assert cells[9]["data-value"] == "1000"  # context
    assert cells[10]["data-value"] == "100"  # output cap
    assert cells[11]["data-value"] == "2026-11-01"  # first seen
    assert cells[12]["data-value"] == "2026-11-01"  # last changed


def test_all_models_columns_match_deal_table_order() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp14"))
    page = build_page(_snapshot(alpha=_entry()), [], settings)
    soup = BeautifulSoup(page, "html.parser")
    deals_head = [th.find("button").get_text() for th in soup.select(".dealsTable thead th")]
    models_head = [
        th.find("button").get_text() for th in soup.select(".modelsTable thead th")
    ]
    # The shared columns keep the same relative order in both tables.
    shared = ["Trend", "Model", "Links", "Go", "Go Plus", "Badges", "In $/M", "Out $/M"]
    assert models_head[: len(shared)] == shared
    assert deals_head[: len(shared)] == shared


def test_all_models_default_sorted_by_go_descending() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp15"))
    snapshot = _snapshot(
        paid60=_entry(key="paid60", id="paid60", name="Paid 60", go_allowance="$60"),
        paid500=_entry(key="paid500", id="paid500", name="Paid 500", go_allowance="$500"),
        unlimited=_entry(
            key="unlimited", id="unlimited", name="Unlimited", is_free=True,
            go_allowance="$∞",
        ),
        noallowance=_entry(
            key="noallowance", id="noallowance", name="No allowance", go_allowance=None
        ),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    names = [th.get_text() for th in soup.select(".modelsTable tbody th")]
    assert names == ["Unlimited", "Paid 500", "Paid 60", "No allowance"]


def test_go_column_defaults_to_descending_sort() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp16"))
    page = build_page(_snapshot(alpha=_entry()), [], settings)
    soup = BeautifulSoup(page, "html.parser")
    for table in soup.find_all("table"):
        headers = table.thead.find_all("th")
        for th in headers:
            expected = "descending" if th.find("button").get_text() == "Go" else "none"
            assert th.get("aria-sort") == expected


def test_heat_tiers_are_granular() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp17"))
    snapshot = _snapshot(
        unlimited=_entry(
            key="unlimited", id="unlimited", name="Unlimited", is_free=True,
            go_allowance="$∞",
        ),
        top=_entry(key="top", id="top", name="Top", go_allowance="$500"),
        high=_entry(key="high", id="high", name="High", go_allowance="$100"),
        mid=_entry(key="mid", id="mid", name="Mid", go_allowance="$60"),
        low=_entry(key="low", id="low", name="Low", go_allowance="$20"),
        basic=_entry(key="basic", id="basic", name="Basic", go_allowance="$15"),
        unlisted=_entry(key="unlisted", id="unlisted", name="Unlisted", go_allowance=None),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    by_name = {
        th.get_text(): th.find_parent("tr") for th in soup.select(".modelsTable tbody th")
    }
    assert "modelsTable-row--tier1" in by_name["Unlimited"].get("class", [])
    assert "modelsTable-row--tier2" in by_name["Top"].get("class", [])
    assert "modelsTable-row--tier2" in by_name["High"].get("class", [])
    assert "modelsTable-row--tier3" in by_name["Mid"].get("class", [])
    assert "modelsTable-row--tier4" in by_name["Low"].get("class", [])
    assert "modelsTable-row--tier5" in by_name["Basic"].get("class", [])
    assert by_name["Unlisted"].get("class", []) == ["modelsTable-row"]
    assert "Top allowance" not in page  # the single hot flag is gone


def test_heat_tiers_apply_to_deal_tables_too() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp20"))
    snapshot = _snapshot(
        promo=_entry(badges=["New"], go_allowance="$500"),
        freebie=_entry(key="freebie", id="freebie", name="Freebie", is_free=True),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    promo_row = soup.select_one(".dealsTable tbody tr")
    free_row = soup.select_one(".freeTable tbody tr")
    assert "dealsTable-row--tier2" in promo_row.get("class", [])
    assert "freeTable-row--tier3" in free_row.get("class", [])  # default $60


def test_allowance_tier_thresholds() -> None:
    from opencode_monitor.html_builder import _allowance_tier

    assert _allowance_tier(_entry(go_allowance="$∞")) == 1
    assert _allowance_tier(_entry(go_allowance="$1,000")) == 2
    assert _allowance_tier(_entry(go_allowance="$100")) == 2
    assert _allowance_tier(_entry(go_allowance="$99")) == 3
    assert _allowance_tier(_entry(go_allowance="$50")) == 3
    assert _allowance_tier(_entry(go_allowance="$49")) == 4
    assert _allowance_tier(_entry(go_allowance="$20")) == 4
    assert _allowance_tier(_entry(go_allowance="$19")) == 5
    assert _allowance_tier(_entry(go_allowance="$1")) == 5
    assert _allowance_tier(_entry(go_allowance=None)) == 0


def test_new_and_recently_changed_flags() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp18"))
    snapshot = _snapshot(
        fresh=_entry(
            key="fresh", id="fresh", name="Fresh", first_seen="2026-11-23",
            last_changed="2026-11-23",
        ),
        updated=_entry(
            key="updated", id="updated", name="Updated", first_seen="2026-11-01",
            last_changed="2026-11-22",
        ),
        stale=_entry(
            key="stale", id="stale", name="Stale", first_seen="2026-11-01",
            last_changed="2026-11-01",
        ),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    by_name = {
        th.get_text(): th.find_parent("tr") for th in soup.select(".modelsTable tbody th")
    }
    fresh = by_name["Fresh"]
    assert "modelsTable-row--new" in fresh.get("class", [])
    assert "New" in fresh.get_text()
    updated = by_name["Updated"]
    assert "modelsTable-row--changed" in updated.get("class", [])
    assert "Recently changed" in updated.get_text()
    stale = by_name["Stale"]
    assert "modelsTable-row--new" not in (stale.get("class", []))
    assert "modelsTable-row--changed" not in (stale.get("class", []))


def test_baseline_inventory_is_not_flagged_new() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp19"))
    # Monitoring began today: everything first seen today is baseline stock.
    history = [
        _history(timestamp="2026-11-23T08:23:00Z", title="Monitoring started")
    ]
    snapshot = _snapshot(
        launchday=_entry(
            key="launchday", id="launchday", name="Launchday",
            first_seen="2026-11-23", last_changed="2026-11-23",
        ),
        postlaunch=_entry(
            key="postlaunch", id="postlaunch", name="Postlaunch",
            first_seen="2026-11-23", last_changed="2026-11-23",
        ),
    )
    page = build_page(snapshot, history, settings)
    soup = BeautifulSoup(page, "html.parser")
    assert soup.select(".modelsTable-row--new") == []

    # Monitoring began earlier: models first seen after that date get flagged.
    history = [_history(timestamp="2026-11-20T08:23:00Z", title="Monitoring started")]
    page = build_page(snapshot, history, settings)
    soup = BeautifulSoup(page, "html.parser")
    flagged = [th.get_text() for th in soup.select(".modelsTable-row--new th")]
    assert flagged == ["Launchday", "Postlaunch"]


def test_allowance_sort_values_handle_edge_cases() -> None:
    from opencode_monitor.html_builder import _allowance_sort_value

    assert _allowance_sort_value("$1,000") == "1000"
    assert _allowance_sort_value("$∞") == "Infinity"
    assert _allowance_sort_value(None) == "-Infinity"


def test_page_has_no_external_assets() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp5"))
    page = build_page(_snapshot(alpha=_entry()), [], settings)
    assert "<script>" in page  # inline sorter only
    assert "<script src" not in page
    assert 'src="http' not in page  # no external assets
    assert 'background-image: url("data:image/png;base64,' in page
    assert "@import" not in page
    # External destinations exist only as user-facing links.
    assert 'href="https://duckduckgo.com/?q=' in page


def test_degraded_page_shows_status_banner() -> None:
    snapshot = _snapshot(alpha=_entry())
    snapshot["console_html_degraded"] = True
    snapshot["console_html_verified_at"] = "2026-11-20T08:23:00Z"
    page = build_page(snapshot, [], _settings(Path("/tmp/opencode/test-tmp6")))
    assert 'role="status"' in page
    assert "could not be refreshed" in page
    assert 'datetime="2026-11-20"' in page


def test_page_escapes_html() -> None:
    snapshot = _snapshot(alpha=_entry(name="<b>Evil & Co</b>"))
    page = build_page(snapshot, [], _settings(Path("/tmp/opencode/test-tmp7")))
    assert "<b>Evil" not in page
    assert "&lt;b&gt;Evil &amp; Co&lt;/b&gt;" in page


def test_empty_states_render_copy() -> None:
    page = build_page(_snapshot(), [], _settings(Path("/tmp/opencode/test-tmp8")))
    assert "No active promotions right now." in page
    assert "No free models right now." in page
    assert "No changes recorded yet." in page


# --- CLI end-to-end ------------------------------------------------------


def test_first_run_writes_everything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    code = main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE])
    assert code == 0
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state["console_html_degraded"] is False
    assert len(state["models"]) > 25
    assert settings.deals_path.exists()
    page = settings.html_path.read_text(encoding="utf-8")
    assert 'role="status"' not in page
    feed = ET.fromstring(settings.feed_path.read_text(encoding="utf-8"))
    assert feed.findtext(f"{ATOM}title") == "OpenCode Go Deals Monitor"
    first_entry = feed.find(f"{ATOM}entry")
    assert first_entry is not None
    assert "Monitoring started" in (first_entry.findtext(f"{ATOM}title") or "")
    history = json.loads(settings.history_path.read_text(encoding="utf-8"))
    assert len(history) == 1
    assert "Baseline snapshot" in history[0]["note"]


def test_second_run_is_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    before = {
        path: path.read_text(encoding="utf-8")
        for path in [
            settings.state_path,
            settings.history_path,
            settings.feed_path,
            settings.html_path,
            settings.deals_path,
        ]
    }
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    after = {
        path: path.read_text(encoding="utf-8")
        for path in [
            settings.state_path,
            settings.history_path,
            settings.feed_path,
            settings.html_path,
            settings.deals_path,
        ]
    }
    assert before == after


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    assert main(["--dry-run", "--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    assert not settings.state_path.exists()
    assert not settings.feed_path.exists()


def test_force_rebuilds_public_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    state_before = settings.state_path.read_text(encoding="utf-8")
    assert main(
        ["--force", "--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]
    ) == 0
    assert settings.state_path.read_text(encoding="utf-8") == state_before
    assert settings.html_path.exists()
    assert settings.feed_path.exists()


def test_missing_json_fixture_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    code = main(["--json-fixture", str(tmp_path / "nope.json")])
    assert code == 1
    assert not settings.state_path.exists()


def test_degraded_console_exits_two_and_carries_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    # Healthy first run.
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    state_before = json.loads(settings.state_path.read_text(encoding="utf-8"))
    glm_before = state_before["models"]["glm53"]["go_allowance"]

    # Degraded run: empty HTML parses 0 models.
    empty_html = tmp_path / "empty.html"
    empty_html.write_text("<html><body></body></html>", encoding="utf-8")
    code = main(["--json-fixture", JSON_FIXTURE, "--html-fixture", str(empty_html)])
    assert code == 2
    state_after = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state_after["console_html_degraded"] is True
    assert state_after["models"]["glm53"]["go_allowance"] == glm_before
    page = settings.html_path.read_text(encoding="utf-8")
    assert 'role="status"' in page

    # Recovery: healthy scrape clears the flag.
    code = main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE])
    assert code == 0
    state_final = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state_final["console_html_degraded"] is False


def test_history_appends_and_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    monkeypatch.setenv("HISTORY_LIMIT", "2")
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    history = json.loads(settings.history_path.read_text(encoding="utf-8"))
    assert len(history) == 1

    # Force a removal: delete an opencode-only model from the JSON fixture so
    # it disappears from both sources at once.
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    payload = json.loads(Path(JSON_FIXTURE).read_text(encoding="utf-8"))
    from opencode_monitor.models import normalise_key

    candidate = next(
        key
        for key, entry in sorted(state["models"].items())
        if entry["providers"] == ["opencode"] and entry["go_allowance"] is None
    )
    opencode_models = payload["opencode"]["models"]
    raw_id = next(
        rid for rid in opencode_models if normalise_key(rid) == candidate
    )
    del opencode_models[raw_id]
    trimmed_json = tmp_path / "trimmed.json"
    trimmed_json.write_text(json.dumps(payload), encoding="utf-8")

    code = main(["--json-fixture", str(trimmed_json), "--html-fixture", HTML_FIXTURE])
    assert code == 0
    history = json.loads(settings.history_path.read_text(encoding="utf-8"))
    assert len(history) == 2
    assert history[-1]["removed"] == [candidate]


def test_change_stamps_last_changed_and_trend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    glm = state["models"]["glm53"]
    baseline = glm["last_changed"]
    assert baseline is not None

    # Change GLM-5.3's input price and give it an older last_changed date,
    # as it would have after days of quiet runs.
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    state["models"]["glm53"]["last_changed"] = "2026-11-01"
    settings.state_path.write_text(json.dumps(state), encoding="utf-8")
    payload = json.loads(Path(JSON_FIXTURE).read_text(encoding="utf-8"))
    payload["opencode-go"]["models"]["glm-5.3"]["cost"]["input"] = 2.75
    bumped = tmp_path / "bumped.json"
    bumped.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["--json-fixture", str(bumped), "--html-fixture", HTML_FIXTURE]) == 0

    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    glm = state["models"]["glm53"]
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert glm["input_cost_per_m"] == 2.75
    assert glm["last_changed"] == today  # stamped by the diff pass
    assert glm["last_trend"] == "down"  # a price rise goes against the reader
    assert glm["first_seen"] <= glm["last_changed"]


def test_link_check_records_verified_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    monkeypatch.setattr(
        "opencode_monitor.cli.url_exists",
        lambda url, **_: url.endswith("/glm-5-3"),
    )
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    glm = state["models"]["glm53"]
    assert glm["info_url"] == "https://artificialanalysis.ai/models/glm-5-3"
    assert glm["info_checked"] is not None
    assert glm["epoch_url"] == "https://epoch.ai/models/glm-5-3"
    assert glm["epoch_checked"] is not None
    assert glm["opencode_url"] == "https://opencode.ai/data/zhipuai/glm-5-3"
    assert glm["opencode_checked"] is not None
    beam = state["models"]["beamfree"]
    assert beam["info_url"] is None
    assert beam["info_checked"] is not None
    assert beam["epoch_url"] is None
    assert beam["epoch_checked"] is not None
    assert beam["opencode_url"] is None
    assert beam["opencode_checked"] is not None
    page = settings.html_path.read_text(encoding="utf-8")
    assert 'href="https://artificialanalysis.ai/models/glm-5-3"' in page
    assert 'href="https://epoch.ai/models/glm-5-3"' in page
    assert 'href="https://opencode.ai/data/zhipuai/glm-5-3"' in page


def test_no_link_check_flag_skips_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))

    def explode(url: str, **_: object) -> bool:
        raise AssertionError("link check should not run")

    monkeypatch.setattr("opencode_monitor.cli.url_exists", explode)
    code = main(
        ["--no-link-check", "--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]
    )
    assert code == 0
    state = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state["models"]["glm53"]["info_url"] is None


def test_changelog_is_readable_anchored_and_newest_first() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp21"))
    history = [
        _history(
            id="urn:opencode-deals:2026-11-20:old111",
            timestamp="2026-11-20T08:00:00Z",
            title="1 model started",
            added=["oldmodel"],
            names={"oldmodel": "Old Model"},
        ),
        _history(
            id="urn:opencode-deals:2026-11-23:abc123",
            timestamp="2026-11-23T08:23:00Z",
            title="2 changes",
            added=[],
            changed=[
                {"key": "glm53", "field": "go_allowance", "old": "$500", "new": "$200"},
                {"key": "glm53", "field": "badges", "old": ["New"], "new": []},
            ],
            names={"glm53": "GLM-5.3"},
        ),
    ]
    snapshot = _snapshot(glm53=_entry(key="glm53", id="glm-5.3", name="GLM-5.3"))
    page = build_page(snapshot, history, settings)
    soup = BeautifulSoup(page, "html.parser")
    entries = soup.select(".changesLog-entry")
    # Reverse chronological: the newest entry renders first.
    assert [entry["id"] for entry in entries] == [
        "chg-2026-11-23-abc123",
        "chg-2026-11-20-old111",
    ]
    newest = entries[0]
    text = newest.get_text(" ", strip=True)
    assert "GLM-5.3" in text
    assert "Go allowance from $500 to $200" in text
    assert "Badges from New to none" in text
    assert "23 November 2026, 08:23 UTC" in text
    # No raw field names or Python reprs anywhere in the changelog.
    changelog = soup.select_one(".changesLog").get_text(" ", strip=True)
    assert "go_allowance" not in changelog
    assert "['" not in changelog
    # Each entry is linkable, and the permalink points at itself.
    permalink = newest.select_one(".changesLog-permalink")
    assert permalink["href"] == "#chg-2026-11-23-abc123"
    assert permalink.get("aria-label") == "Link to this entry"
    assert "#chg-2026-11-23-abc123" in page  # target highlight rule present
    assert "changesLog-entry:target" in page


def test_changelog_falls_back_to_snapshot_names() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp22"))
    history = [
        _history(
            title="1 change",
            added=[],
            changed=[{"key": "glm53", "field": "is_free", "old": False, "new": True}],
            names={},  # older entries carry no names map
        )
    ]
    snapshot = _snapshot(glm53=_entry(key="glm53", id="glm-5.3", name="GLM-5.3"))
    page = build_page(snapshot, history, settings)
    soup = BeautifulSoup(page, "html.parser")
    text = soup.select_one(".changesLog").get_text(" ", strip=True)
    assert "GLM-5.3" in text
    assert "Free tier from no to yes" in text


def test_atom_entry_links_match_changelog_anchors() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp23"))
    history = [
        _history(
            added=[],
            title="1 change",
            changed=[
                {"key": "glm53", "field": "input_cost_per_m", "old": 1.4, "new": 2.75}
            ],
            names={"glm53": "GLM-5.3"},
        )
    ]
    feed_xml = build_feed(history, settings)
    root = ET.fromstring(feed_xml)
    entry = root.find(f"{ATOM}entry")
    link = entry.find(f"{ATOM}link[@rel='alternate']")
    assert link is not None
    assert link.get("href", "").endswith("/#chg-2026-11-23-abc123")
    content = entry.findtext(f"{ATOM}content") or ""
    assert "GLM-5.3: Input price from $1.40/M to $2.75/M" in content

    snapshot = _snapshot(glm53=_entry(key="glm53", id="glm-5.3", name="GLM-5.3"))
    page = build_page(snapshot, history, settings)
    assert 'id="chg-2026-11-23-abc123"' in page


def test_trend_column_shows_direction() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp24"))
    snapshot = _snapshot(
        up=_entry(key="up", id="up", name="Up", last_trend="up"),
        down=_entry(key="down", id="down", name="Down", last_trend="down"),
        flat=_entry(key="flat", id="flat", name="Flat", last_trend=None),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    by_name = {
        th.get_text(): th.find_parent("tr") for th in soup.select(".modelsTable tbody th")
    }
    up_cell = by_name["Up"].find("td")
    assert "▲" in up_cell.get_text()
    assert up_cell.find("span", class_="modelsTable-trend") is not None
    down_cell = by_name["Down"].find("td")
    assert "▼" in down_cell.get_text()
    assert down_cell.find("span", class_="modelsTable-trend--down") is not None
    assert by_name["Flat"].find("td").get_text() == "—"
    # First column in every table.
    for table in soup.find_all("table"):
        assert table.thead.find("th").find("button").get_text() == "Trend"
    assert "--color-up" in page and "--color-down" in page
    assert "modelsTable-trend--down" in page


def test_changelog_markers_show_direction() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp25"))
    history = [
        _history(
            title="3 changes",
            added=[],
            changed=[
                {"key": "a", "field": "go_allowance", "old": "$60", "new": "$120"},
                {"key": "a", "field": "input_cost_per_m", "old": 1.0, "new": 2.0},
                {"key": "a", "field": "badges", "old": ["New"], "new": ["New", "Promo"]},
            ],
            names={"a": "Model A"},
        )
    ]
    page = build_page(_snapshot(), history, settings)
    soup = BeautifulSoup(page, "html.parser")
    items = soup.select(".changesLog-items li")
    # Allowance up: green up triangle with hidden "Better:" text.
    assert "▲" in items[0].get_text()
    assert "Better:" in items[0].get_text()
    # Cost up: red down triangle with hidden "Worse:" text.
    assert "▼" in items[1].get_text()
    assert "Worse:" in items[1].get_text()
    # Badge count up: better.
    assert "Better:" in items[2].get_text()
    # Glyphs are hidden from assistive tech; the direction is spoken as a word.
    assert items[0].find("span", class_="changesLog-marker").get("aria-hidden") == "true"
    assert items[1].find("span", class_="changesLog-marker--down") is not None


def test_changelog_started_and_ended_markers() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp26"))
    history = [
        _history(
            title="1 model started, 1 model ended",
            added=["newbie"],
            removed=["leaver"],
            names={"newbie": "Newbie", "leaver": "Leaver"},
        )
    ]
    page = build_page(_snapshot(), history, settings)
    soup = BeautifulSoup(page, "html.parser")
    items = soup.select(".changesLog-items li")
    started = next(item for item in items if "Newbie" in item.get_text())
    ended = next(item for item in items if "Leaver" in item.get_text())
    assert "▲" in started.get_text() and "Better:" in started.get_text()
    assert "▼" in ended.get_text() and "Worse:" in ended.get_text()


def test_model_names_link_when_verified() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp27"))
    snapshot = _snapshot(
        linked=_entry(
            key="linked", id="linked", name="Linked",
            info_url="https://artificialanalysis.ai/models/linked",
        ),
        plain=_entry(key="plain", id="plain", name="Plain"),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    link = soup.select_one('a[href="https://artificialanalysis.ai/models/linked"]')
    assert link is not None
    assert link.get_text() == "Linked"
    icon = link.find_previous_sibling("span")
    assert icon is not None
    assert "linkIcon--aa" in icon.get("class", [])
    assert icon.get("aria-hidden") == "true"
    assert "DuckDuckGo AI search" in page


def test_uncovered_models_link_to_duckduckgo_ai() -> None:
    from urllib.parse import quote_plus

    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp29"))
    snapshot = _snapshot(plain=_entry(key="plain", id="plain", name="Plain Model"))
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    link = soup.find("a", string="Plain Model")
    assert link is not None
    href = link["href"]
    assert href.startswith("https://duckduckgo.com/?q=")
    expected_prompt = (
        "What is Plain Model? Summarise its context window, price and coding "
        "benchmarks, plus community opinion and sentiment from Hacker News, "
        "Lobsters, Reddit and similar sites. Cite sources."
    )
    assert quote_plus(expected_prompt) in href
    assert href.endswith("&ia=chat&prompt=1")
    icon = link.find_previous_sibling("span")
    assert icon is not None
    assert "linkIcon--ddg" in icon.get("class", [])


def test_section_spacing_is_consistent() -> None:
    settings = _settings(Path("/tmp/opencode/test-tmp28"))
    page = build_page(_snapshot(), [], settings)
    assert "main > * + * { margin-top: var(--space-xl); }" in page
    assert '<h2 class="changesSection-heading" id="changes-heading">' in page
    assert ".changesSection-heading { margin-bottom: var(--space-m); }" in page
    assert "p + p { margin-top: var(--space-s); }" in page
    # Wrapped changelog lines align under the text, not the marker.
    assert "text-indent: -1.4em;" in page
    # Links are text-coloured and underlined; no accent colour remains.
    assert "a { color: inherit; text-decoration: underline; }" in page
    assert "outline: 2px solid var(--color-text);" in page
    assert "solid var(--color-text);" in page
    assert "--color-accent" not in page


def test_force_run_populates_links_without_history_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    assert main(
        ["--no-link-check", "--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]
    ) == 0
    history_before = settings.history_path.read_text(encoding="utf-8")
    state_before = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state_before["models"]["glm53"]["info_url"] is None

    monkeypatch.setattr(
        "opencode_monitor.cli.url_exists",
        lambda url, **_: url.endswith("/glm-5-3"),
    )
    assert main(
        ["--force", "--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]
    ) == 0
    state_after = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert state_after["models"]["glm53"]["info_url"].endswith("/glm-5-3")
    assert state_after["models"]["glm53"]["epoch_url"].endswith("/glm-5-3")
    assert state_after["models"]["glm53"]["opencode_url"].endswith("/glm-5-3")
    # A link-only metadata change must not add a changelog event.
    assert settings.history_path.read_text(encoding="utf-8") == history_before


def test_links_column_order_and_presence() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp30"))
    snapshot = _snapshot(
        full=_entry(
            key="full", id="full", name="Full Model",
            info_url="https://artificialanalysis.ai/models/full-model",
            epoch_url="https://epoch.ai/models/full-model",
            opencode_url="https://opencode.ai/data/maker/full-model",
        ),
        aa_only=_entry(
            key="aaonly", id="aaonly", name="AA Only",
            info_url="https://artificialanalysis.ai/models/aa-only",
        ),
        bare=_entry(key="bare", id="bare", name="Bare"),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    cells = {
        th.get_text(): th.find_parent("tr").select_one(".linksCell")
        for th in soup.select(".modelsTable tbody th")
    }
    full_links = [a.get_text() for a in cells["Full Model"].select("a")]
    assert full_links == ["DDG", "OpenCode", "AA", "Epoch"]
    aa_links = [a.get_text() for a in cells["AA Only"].select("a")]
    assert aa_links == ["DDG", "AA"]
    bare_links = [a.get_text() for a in cells["Bare"].select("a")]
    assert bare_links == ["DDG"]
    # Destinations are named for assistive tech, not just by icon.
    assert cells["Full Model"].select_one("a")["aria-label"] == (
        "DuckDuckGo AI search for Full Model"
    )
    labels = [a["aria-label"] for a in cells["Full Model"].select("a")]
    assert labels[1] == "OpenCode page for Full Model"
    assert labels[2] == "Artificial Analysis page for Full Model"
    assert labels[3] == "Epoch AI page for Full Model"
    # The new column appears in every table.
    for table in soup.find_all("table"):
        headers = [th.find("button").get_text() for th in table.thead.find_all("th")]
        assert "Links" in headers


def test_model_name_prefers_opencode_page() -> None:
    from bs4 import BeautifulSoup

    settings = _settings(Path("/tmp/opencode/test-tmp31"))
    snapshot = _snapshot(
        page=_entry(
            key="page", id="page", name="Page Model",
            opencode_url="https://opencode.ai/data/maker/page-model",
            info_url="https://artificialanalysis.ai/models/page-model",
        ),
        fallback=_entry(
            key="fallback", id="fallback", name="Fallback",
            info_url="https://artificialanalysis.ai/models/fallback",
        ),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    page_link = soup.find("a", string="Page Model")
    assert page_link["href"] == "https://opencode.ai/data/maker/page-model"
    icon = page_link.find_previous_sibling("span")
    assert "linkIcon--opencode" in icon.get("class", [])
    fallback_link = soup.find("a", string="Fallback")
    assert "artificialanalysis.ai" in fallback_link["href"]
    assert "linkIcon--aa" in fallback_link.find_previous_sibling("span").get("class", [])


def test_step_summary_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("PUBLIC_DIR", str(settings.public_dir))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["--json-fixture", JSON_FIXTURE, "--html-fixture", HTML_FIXTURE]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "Status: initialised" in text
    assert "Models tracked:" in text
