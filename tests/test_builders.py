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
    assert '<th scope="row">Alpha</th>' in page
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
    assert '<h2 id="promos-heading">Promos</h2>' in page
    assert '<h2 id="free-heading">Free models</h2>' in page
    assert '<h2 id="all-models-heading">All tracked models</h2>' in page


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
            assert th.get("aria-sort") == "none"
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
        gamma=_entry(key="gamma", id="gamma", name="Gamma", is_free=True, badges=["Limited time"]),
    )
    page = build_page(snapshot, [], settings)
    soup = BeautifulSoup(page, "html.parser")
    promos = soup.select_one("#promos-heading").find_parent("details")
    frees = soup.select_one("#free-heading").find_parent("details")
    promo_names = [th.get_text() for th in promos.select(".dealsTable tbody th")]
    free_names = [th.get_text() for th in frees.select(".freeTable tbody th")]
    assert promo_names == ["Alpha"]  # free models never appear in promos
    assert free_names == ["Beta", "Gamma"]


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
    # Go / Go Plus / costs / limits carry numeric data-value attributes.
    assert cells[6]["data-value"] == "60"  # $60
    assert cells[7]["data-value"] == "120"  # $120
    assert cells[4]["data-value"] == "1.0"  # In $/M
    assert cells[5]["data-value"] == "2.0"  # Out $/M
    assert cells[2]["data-value"] == "1000"  # context
    assert cells[3]["data-value"] == "100"  # output cap
    # Dates fall back to their ISO text; IDs sort as plain text.
    assert cells[9]["data-value"] == "2026-11-01"  # first seen
    assert cells[10]["data-value"] == "2026-11-01"  # last changed
    assert cells[0].get("data-value") is None


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
    assert "src=" not in page
    assert "http://" not in page
    assert "https://" not in page
    assert "@import" not in page


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


def test_change_stamps_last_changed(
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
    assert glm["first_seen"] <= glm["last_changed"]


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
