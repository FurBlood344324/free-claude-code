"""Provider model-list response parsing helpers."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from free_claude_code.application.model_metadata import (
    ModelCapability,
)
from free_claude_code.application.model_metadata import (
    ProviderModelInfo as _ProviderModelInfo,
)


class ModelListResponseError(ValueError):
    """A provider model-list response cannot be parsed safely."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# Field names commonly used by OpenAI-compatible ``/models`` responses that
# advertise per-model token limits (OpenRouter, some gateways).
_CONTEXT_LENGTH_FIELDS = ("context_length", "context_window", "max_context_length")
_MAX_OUTPUT_FIELDS = ("max_completion_tokens", "max_tokens")


def model_capability_from_item(item: Any) -> ModelCapability:
    """Return provider-advertised token limits from one model-list item."""
    return ModelCapability(
        context_window=_first_positive_int(item, _CONTEXT_LENGTH_FIELDS),
        max_output_tokens=_first_positive_int(
            item, _MAX_OUTPUT_FIELDS, nested_fields=("top_provider",)
        ),
    )


def model_infos_from_ids(
    model_ids: Iterable[str], *, supports_thinking: bool | None = None
) -> frozenset[_ProviderModelInfo]:
    """Build unknown-capability model metadata from plain provider model ids."""
    return frozenset(
        _ProviderModelInfo(model_id=model_id, supports_thinking=supports_thinking)
        for model_id in model_ids
        if model_id.strip()
    )


def extract_openai_model_infos(
    payload: Any, *, provider_name: str
) -> frozenset[_ProviderModelInfo]:
    """Extract model metadata from an OpenAI-compatible ``/models`` response."""
    model_infos: set[_ProviderModelInfo] = set()
    for item in model_list_items(payload, provider_name=provider_name):
        model_id = _field(item, "id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise _malformed(provider_name, "expected every data item to include id")
        capability = model_capability_from_item(item)
        model_infos.add(
            _ProviderModelInfo(
                model_id=model_id,
                context_window=capability.context_window,
                max_output_tokens=capability.max_output_tokens,
            )
        )

    if not model_infos:
        raise _malformed(provider_name, "response did not include any model ids")
    return frozenset(model_infos)


def extract_tool_capable_model_infos(
    payload: Any, *, provider_name: str
) -> frozenset[_ProviderModelInfo]:
    """Extract tool-capable models with ``supported_parameters`` metadata."""
    data = model_list_items(payload, provider_name=provider_name)

    model_infos: set[_ProviderModelInfo] = set()
    for item in data:
        model_id = _field(item, "id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise _malformed(provider_name, "expected every data item to include id")

        supported_parameters = _field(item, "supported_parameters")
        if not _is_sequence(supported_parameters):
            continue
        supported_parameter_names = {
            param for param in supported_parameters if isinstance(param, str)
        }
        if supported_parameter_names.isdisjoint({"tools", "tool_choice"}):
            continue
        capability = model_capability_from_item(item)
        model_infos.add(
            _ProviderModelInfo(
                model_id=model_id,
                supports_thinking="reasoning" in supported_parameter_names,
                context_window=capability.context_window,
                max_output_tokens=capability.max_output_tokens,
            )
        )

    return frozenset(model_infos)


def model_list_items(payload: Any, *, provider_name: str) -> tuple[Any, ...]:
    """Return a validated OpenAI-shaped model-list data array."""
    data = _field(payload, "data")
    if not _is_sequence(data):
        raise _malformed(provider_name, "expected top-level data array")
    return tuple(data)


def _field(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _first_positive_int(
    item: Any,
    field_names: Sequence[str],
    *,
    nested_fields: Sequence[str] = (),
) -> int | None:
    """Return the first positive integer field value, including nested objects."""
    for name in field_names:
        value = _field(item, name)
        if _is_positive_int(value):
            return value
    for nested_name in nested_fields:
        nested = _field(item, nested_name)
        for name in field_names:
            value = _field(nested, name)
            if _is_positive_int(value):
                return value
    return None


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, str | bytes | bytearray
    )


def _malformed(provider_name: str, reason: str) -> ModelListResponseError:
    return ModelListResponseError(
        f"{provider_name} model-list response is malformed: {reason}"
    )
