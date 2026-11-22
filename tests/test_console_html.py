"""console_html tests against the captured live fixture."""

from __future__ import annotations

from pathlib import Path

from opencode_monitor.console_html import parse_console_html
from opencode_monitor.models import normalise_key

FIXTURE = Path(__file__).parent / "fixtures" / "console-go.html"
HTML = FIXTURE.read_text(encoding="utf-8")


def test_parses_every_row() -> None:
    models = parse_console_html(HTML)
    row_count = HTML.count('data-layer="model-row"')
    assert len(models) == row_count
    assert row_count >= 25  # sanity: the live table is large


def test_glm_53_allowances() -> None:
    models = parse_console_html(HTML)
    glm = models[normalise_key("glm-5.3")]
    assert glm.name == "GLM-5.3"
    assert glm.go_allowance == "$500"
    assert glm.go_plus_allowance == "$1,000"
    assert glm.is_free is False


def test_badges_captured() -> None:
    models = parse_console_html(HTML)
    new_models = [m for m in models.values() if "New" in m.badges]
    limited = [m for m in models.values() if "Limited time" in m.badges]
    regions = [m for m in models.values() if "Limited regions" in m.badges]
    assert new_models, "fixture advertises at least one New badge"
    assert limited, "fixture advertises at least one Limited time note"
    assert regions, "fixture advertises at least one Limited regions note"


def test_free_models_detected() -> None:
    models = parse_console_html(HTML)
    assert models[normalise_key("beam-free")].is_free is True
    assert models[normalise_key("longcat-2.5-free")].is_free is True
    assert models[normalise_key("glm-5.3")].is_free is False


def test_hidden_rows_are_captured() -> None:
    models = parse_console_html(HTML)
    # The console page ships some rows with a `hidden` attribute; the data
    # is still in the DOM and must be captured.
    assert normalise_key("beam-free") in models


def test_empty_html_yields_no_models() -> None:
    assert parse_console_html("<html><body></body></html>") == {}


def test_minimal_row_parses() -> None:
    html = """
    <table><tbody>
    <tr data-model="test-model">
      <th scope="row">
        <span data-layer="model-name" title="Test Model">Test Model</span>
        <span class="console-go-models-new">New</span>
      </th>
      <td data-allowance-type="usage">
        <div aria-hidden="true">
          <span data-plan="go">
            <span data-layer="current-value">$10</span>
          </span>
          <span data-plan="go-plus">
            <span data-layer="current-value">$20</span>
          </span>
        </div>
        <span class="sr-only">Go: $10; Go Plus: $20</span>
      </td>
    </tr>
    </tbody></table>
    """
    models = parse_console_html(html)
    model = models["testmodel"]
    assert model.name == "Test Model"
    assert model.go_allowance == "$10"
    assert model.go_plus_allowance == "$20"
    assert model.badges == ("New",)
    assert model.is_free is False
