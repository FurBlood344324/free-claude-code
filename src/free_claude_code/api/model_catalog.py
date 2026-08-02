"""Model-list response construction for Claude-compatible clients."""

from typing import Literal

from pydantic import BaseModel

from free_claude_code.application.model_capabilities import resolve_model_capability
from free_claude_code.application.model_metadata import (
    ModelCapability,
    ProviderModelInfo,
)
from free_claude_code.application.ports import RequestRuntimePort
from free_claude_code.config.model_refs import configured_chat_model_refs
from free_claude_code.config.settings import Settings
from free_claude_code.core.gateway_model_ids import (
    gateway_model_id,
    no_thinking_gateway_model_id,
)

DISCOVERED_MODEL_CREATED_AT = "1970-01-01T00:00:00Z"


class ModelResponse(BaseModel):
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "free-claude-code"
    created_at: str
    display_name: str
    id: str
    type: Literal["model"] = "model"
    context_window: int | None = None
    max_output_tokens: int | None = None


class ModelsListResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelResponse]
    first_id: str | None
    has_more: bool
    last_id: str | None


SUPPORTED_CLAUDE_MODELS = [
    ModelResponse(
        id="claude-fable-5",
        display_name="Claude Fable 5",
        created_at="2026-06-09T00:00:00Z",
    ),
    ModelResponse(
        id="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        created_at="2025-05-14T00:00:00Z",
    ),
    ModelResponse(
        id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        created_at="2025-05-14T00:00:00Z",
    ),
    ModelResponse(
        id="claude-haiku-4-20250514",
        display_name="Claude Haiku 4",
        created_at="2025-05-14T00:00:00Z",
    ),
    ModelResponse(
        id="claude-3-opus-20240229",
        display_name="Claude 3 Opus",
        created_at="2024-02-29T00:00:00Z",
    ),
    ModelResponse(
        id="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet",
        created_at="2024-10-22T00:00:00Z",
    ),
    ModelResponse(
        id="claude-3-haiku-20240307",
        display_name="Claude 3 Haiku",
        created_at="2024-03-07T00:00:00Z",
    ),
    ModelResponse(
        id="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku",
        created_at="2024-10-22T00:00:00Z",
    ),
]


def build_models_list_response(
    settings: Settings, runtime: RequestRuntimePort
) -> ModelsListResponse:
    """Return configured, cached, and compatibility model ids."""
    models: list[ModelResponse] = []
    seen: set[str] = set()

    for ref in configured_chat_model_refs(settings):
        cached = runtime.cached_model_info(ref.provider_id, ref.model_id)
        capability = _configured_model_capability(cached, ref.model_id)
        _append_provider_model_variants(
            models,
            seen,
            ref.model_ref,
            supports_thinking=(
                cached.supports_thinking if cached is not None else None
            ),
            capability=capability,
        )

    for model_info in runtime.cached_prefixed_model_infos():
        _append_provider_model_variants(
            models,
            seen,
            model_info.model_id,
            supports_thinking=model_info.supports_thinking,
            capability=model_info.capability,
        )

    for model in SUPPORTED_CLAUDE_MODELS:
        _append_unique_model(models, seen, _alias_model_response(model))

    return ModelsListResponse(
        data=models,
        first_id=models[0].id if models else None,
        has_more=False,
        last_id=models[-1].id if models else None,
    )


def _configured_model_capability(
    cached: ProviderModelInfo | None, model_id: str
) -> ModelCapability:
    """Resolve capability for a configured ref from cache or built-in data."""
    provider_supplied = cached.capability if cached is not None else None
    return resolve_model_capability(model_id, provider_supplied=provider_supplied)


def _alias_model_response(model: ModelResponse) -> ModelResponse:
    """Resolve built-in token limits for a fixed Claude compatibility alias."""
    capability = resolve_model_capability(model.id)
    if capability.context_window is None and capability.max_output_tokens is None:
        return model
    return ModelResponse(
        id=model.id,
        display_name=model.display_name,
        created_at=model.created_at,
        context_window=capability.context_window,
        max_output_tokens=capability.max_output_tokens,
    )


def _discovered_model_response(
    model_id: str,
    *,
    display_name: str,
    capability: ModelCapability | None = None,
) -> ModelResponse:
    resolved = resolve_model_capability(model_id, provider_supplied=capability)
    return ModelResponse(
        id=model_id,
        display_name=display_name,
        created_at=DISCOVERED_MODEL_CREATED_AT,
        context_window=resolved.context_window,
        max_output_tokens=resolved.max_output_tokens,
    )


def _append_unique_model(
    models: list[ModelResponse], seen: set[str], model: ModelResponse
) -> None:
    if model.id in seen:
        return
    seen.add(model.id)
    models.append(model)


def _append_provider_model_variants(
    models: list[ModelResponse],
    seen: set[str],
    provider_model_ref: str,
    *,
    supports_thinking: bool | None = None,
    capability: ModelCapability | None = None,
) -> None:
    if supports_thinking is not False:
        _append_unique_model(
            models,
            seen,
            _discovered_model_response(
                gateway_model_id(provider_model_ref),
                display_name=provider_model_ref,
                capability=capability,
            ),
        )
    _append_unique_model(
        models,
        seen,
        _discovered_model_response(
            no_thinking_gateway_model_id(provider_model_ref),
            display_name=f"{provider_model_ref} (no thinking)",
            capability=capability,
        ),
    )
