"""models_api tests against the captured live fixture."""

from __future__ import annotations

import json
from pathlib import Path

from opencode_monitor.models_api import parse_models_api

FIXTURE = Path(__file__).parent / "fixtures" / "models.dev.json"


def _load() -> dict:
    with FIXTURE.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_parses_both_providers() -> None:
    models = parse_models_api(_load())
    assert models, "fixture should yield models"
    providers = {p for model in models.values() for p in model.providers}
    assert providers <= {"opencode-go", "opencode"}
    assert any(model.providers == ("opencode-go",) for model in models.values())
    assert any("opencode" in model.providers for model in models.values())


def test_glm_53_fields() -> None:
    models = parse_models_api(_load())
    glm = models.get("glm53")
    assert glm is not None, "GLM-5.3 should normalise to glm53"
    assert glm.id == "glm-5.3"
    assert glm.name == "GLM-5.3"
    assert glm.context_limit == 1_000_000
    assert glm.output_limit == 131_072
    assert glm.input_cost_per_m == 1.4
    assert glm.output_cost_per_m == 4.4
    assert glm.is_free is False


def test_free_models_flagged() -> None:
    models = parse_models_api(_load())
    free_models = {key for key, model in models.items() if model.is_free}
    assert "beamfree" in free_models  # id ends with -free and costs are zero
    paid = {key for key, model in models.items() if not model.is_free}
    assert "glm53" in paid


def test_model_in_both_providers_records_both() -> None:
    payload = {
        "opencode-go": {
            "models": {
                "shared": {
                    "id": "shared",
                    "name": "Shared",
                    "limit": {"context": 10, "output": 5},
                    "cost": {"input": 1, "output": 2},
                }
            }
        },
        "opencode": {
            "models": {
                "shared": {
                    "id": "shared",
                    "name": "Shared",
                    "limit": {"context": 99, "output": 99},
                    "cost": {"input": 9, "output": 9},
                }
            }
        },
    }
    models = parse_models_api(payload)
    assert models["shared"].providers == ("opencode-go", "opencode")
    # opencode-go fields win.
    assert models["shared"].context_limit == 10
    assert models["shared"].input_cost_per_m == 1


def test_missing_cost_and_limit_fields() -> None:
    payload = {"opencode-go": {"models": {"bare": {"id": "bare", "name": "Bare"}}}}
    model = parse_models_api(payload)["bare"]
    assert model.context_limit is None
    assert model.output_limit is None
    assert model.input_cost_per_m is None
    assert model.output_cost_per_m is None
    assert model.is_free is False


def test_non_object_payload_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="not a JSON object"):
        parse_models_api(["nope"])


def test_artificial_analysis_slug() -> None:
    from opencode_monitor.models import artificial_analysis_url

    assert (
        artificial_analysis_url("GLM-5.3")
        == "https://artificialanalysis.ai/models/glm-5-3"
    )
    assert (
        artificial_analysis_url("DeepSeek V4.1 Flash 1017")
        == "https://artificialanalysis.ai/models/deepseek-v4-1-flash-1017"
    )
    assert (
        artificial_analysis_url("LongCat 2.5 Free")
        == "https://artificialanalysis.ai/models/longcat-2-5-free"
    )


def test_allowance_value() -> None:
    from opencode_monitor.models import allowance_value

    assert allowance_value("$1,000") == 1000
    assert allowance_value(None) == float("-inf")
    assert allowance_value("$∞") == float("inf")
    assert allowance_value("$15") < allowance_value("$60") < allowance_value("$∞")


def test_duckduckgo_ai_url() -> None:
    from opencode_monitor.models import duckduckgo_ai_url

    url = duckduckgo_ai_url("Icy Model")
    assert url.startswith("https://duckduckgo.com/?q=")
    assert url.endswith("&ia=chat&prompt=1")
    assert "What+is+Icy+Model%3F" in url
    assert "community+opinion+and+sentiment" in url
    assert "Hacker+News%2C+Lobsters%2C+Reddit" in url
    assert "Cite+sources" in url
