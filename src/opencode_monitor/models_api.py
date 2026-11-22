"""Parser for models.dev/api.json (opencode-go and opencode providers)."""

from __future__ import annotations

from typing import Any

from .models import ApiModel, normalise_key

# opencode-go entries win when a model appears in both providers.
PROVIDER_ORDER = ("opencode-go", "opencode")


def _is_free(model_id: str, cost: dict[str, Any] | None) -> bool:
    if model_id.endswith("-free"):
        return True
    if cost is None:
        return False
    input_cost = cost.get("input")
    output_cost = cost.get("output")
    return input_cost == 0 and output_cost == 0


def parse_models_api(payload: Any) -> dict[str, ApiModel]:
    """Extract models from the opencode-go and opencode provider objects.

    Returns a map keyed by normalised model ID. When the same model appears
    under both providers, the opencode-go fields win and both provider names
    are recorded.
    """
    if not isinstance(payload, dict):
        msg = "models.dev payload is not a JSON object"
        raise ValueError(msg)

    models: dict[str, ApiModel] = {}
    for provider in PROVIDER_ORDER:
        provider_obj = payload.get(provider)
        if not isinstance(provider_obj, dict):
            continue
        entries = provider_obj.get("models")
        if not isinstance(entries, dict):
            continue
        for raw_id, raw_model in entries.items():
            if not isinstance(raw_model, dict):
                continue
            model_id = raw_model.get("id") or str(raw_id)
            key = normalise_key(model_id)
            existing = models.get(key)
            if existing is not None:
                if provider not in existing.providers:
                    models[key] = ApiModel(
                        key=existing.key,
                        id=existing.id,
                        canonical_model_id=existing.canonical_model_id,
                        name=existing.name,
                        providers=(*existing.providers, provider),
                        context_limit=existing.context_limit,
                        output_limit=existing.output_limit,
                        input_cost_per_m=existing.input_cost_per_m,
                        output_cost_per_m=existing.output_cost_per_m,
                        is_free=existing.is_free,
                    )
                continue
            limit = raw_model.get("limit") or {}
            cost = raw_model.get("cost")
            models[key] = ApiModel(
                key=key,
                id=model_id,
                canonical_model_id=raw_model.get("canonical_model_id"),
                name=str(raw_model.get("name") or model_id),
                providers=(provider,),
                context_limit=limit.get("context"),
                output_limit=limit.get("output"),
                input_cost_per_m=cost.get("input") if cost else None,
                output_cost_per_m=cost.get("output") if cost else None,
                is_free=_is_free(model_id, cost),
            )
    return models
