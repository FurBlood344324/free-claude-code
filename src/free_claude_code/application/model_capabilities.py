"""Known-model capability fallback used by the model catalog API.

Providers that advertise token limits through their model-list endpoint take
precedence (see :mod:`providers.model_listing`). This catalog is the fallback
for OpenAI-compatible providers whose ``/models`` responses only carry model
ids (OpenCode Zen/Go, Wafer, NVIDIA NIM, and most local servers).

Values mirror the OpenCode Zen/Go public model catalog so FCC-discovered
models agree with the limits pi advertises for the same models.
"""

from dataclasses import dataclass

from .model_metadata import ModelCapability


@dataclass(frozen=True, slots=True)
class _KnownModel:
    context_window: int
    max_output_tokens: int


def _known(context_window: int, max_output_tokens: int) -> _KnownModel:
    return _KnownModel(context_window, max_output_tokens)


# Keyed by normalized model id (lowercase). Provider prefixes are stripped
# during lookup so ``anthropic/claude-opus-4-5`` and ``claude-opus-4-5``
# resolve to the same entry.
_KNOWN_CAPABILITIES: dict[str, _KnownModel] = {
    # Claude family (OpenCode Zen and Claude aliases).
    "claude-fable-5": _known(1000000, 128000),
    "claude-opus-5": _known(1000000, 128000),
    "claude-opus-4-8": _known(1000000, 128000),
    "claude-opus-4-7": _known(1000000, 128000),
    "claude-opus-4-6": _known(1000000, 128000),
    "claude-opus-4-5": _known(200000, 64000),
    "claude-opus-4-1": _known(200000, 32000),
    "claude-opus-4-20250514": _known(200000, 32000),
    "claude-sonnet-5": _known(1000000, 128000),
    "claude-sonnet-4-6": _known(1000000, 64000),
    "claude-sonnet-4-5": _known(200000, 64000),
    "claude-sonnet-4": _known(200000, 64000),
    "claude-sonnet-4-20250514": _known(200000, 64000),
    "claude-haiku-4-5": _known(200000, 64000),
    "claude-haiku-4-20250514": _known(200000, 64000),
    "claude-3-opus-20240229": _known(200000, 4096),
    "claude-3-5-sonnet-20241022": _known(200000, 8192),
    "claude-3-haiku-20240307": _known(200000, 4096),
    "claude-3-5-haiku-20241022": _known(200000, 8192),
    # GPT-5 family (OpenCode Zen).
    "gpt-5": _known(400000, 128000),
    "gpt-5-codex": _known(400000, 128000),
    "gpt-5-nano": _known(400000, 128000),
    "gpt-5.1": _known(400000, 128000),
    "gpt-5.1-codex": _known(400000, 128000),
    "gpt-5.1-codex-max": _known(400000, 128000),
    "gpt-5.1-codex-mini": _known(400000, 128000),
    "gpt-5.2": _known(400000, 128000),
    "gpt-5.2-codex": _known(400000, 128000),
    "gpt-5.3-codex": _known(400000, 128000),
    "gpt-5.3-codex-spark": _known(400000, 128000),
    "gpt-5.4": _known(272000, 128000),
    "gpt-5.4-mini": _known(400000, 128000),
    "gpt-5.4-nano": _known(400000, 128000),
    "gpt-5.4-pro": _known(1050000, 128000),
    "gpt-5.5": _known(1050000, 128000),
    "gpt-5.5-pro": _known(1050000, 128000),
    "gpt-5.6-sol": _known(1050000, 128000),
    "gpt-5.6-terra": _known(1050000, 128000),
    "gpt-5.6-luna": _known(1050000, 128000),
    # DeepSeek (OpenCode Go and direct DeepSeek API).
    "deepseek-v4-flash": _known(1000000, 384000),
    "deepseek-v4-flash-free": _known(200000, 128000),
    "deepseek-v4-pro": _known(1000000, 384000),
    "deepseek-chat": _known(128000, 8192),
    "deepseek-reasoner": _known(128000, 8192),
    # Gemini (Google AI Studio OpenAI-compat layer and OpenCode Zen).
    "gemini-3-flash": _known(1048576, 65536),
    "gemini-3.1-pro": _known(1048576, 65536),
    "gemini-3.5-flash": _known(1048576, 65536),
    "gemini-3.5-flash-lite": _known(1048576, 65536),
    "gemini-3.6-flash": _known(1048576, 65536),
    "gemini-2.5-pro": _known(1048576, 65536),
    "gemini-2.5-flash": _known(1048576, 65536),
    "gemini-2.0-flash": _known(1048576, 8192),
    # Other OpenCode Zen/Go models.
    "qwen3.5-plus": _known(262144, 65536),
    "qwen3.6-plus": _known(262144, 65536),
    "qwen3.7-plus": _known(262144, 65536),
    "qwen3.7-max": _known(262144, 65536),
    "glm-5": _known(204800, 131072),
    "glm-5.1": _known(204800, 131072),
    "glm-5.2": _known(1000000, 131072),
    "grok-4.5": _known(500000, 500000),
    "grok-build-0.1": _known(256000, 256000),
    "kimi-k3": _known(1048576, 131072),
    "kimi-k2.7-code": _known(262144, 262144),
    "kimi-k2.6": _known(262144, 65536),
    "kimi-k2.5": _known(262144, 65536),
    "minimax-m3": _known(512000, 128000),
    "minimax-m2.7": _known(204800, 131072),
    "minimax-m2.5": _known(204800, 131072),
    "mimo-v2-pro": _known(1048576, 131072),
    "mimo-v2.5": _known(1048576, 131072),
    "mimo-v2.5-pro": _known(1048576, 131072),
    "mimo-v2-omni": _known(1048576, 131072),
    "mimo-v2.5-free": _known(200000, 32000),
    "nemotron-3-ultra-free": _known(1000000, 128000),
    "big-pickle": _known(200000, 32000),
    "hy3": _known(200000, 128000),
    "hy3-preview": _known(200000, 128000),
    "laguna-s-2.1-free": _known(256000, 32000),
    "ling-3.0-flash-free": _known(262144, 32768),
    "north-mini-code-free": _known(256000, 64000),
}


def _known_capability(model_id: str) -> _KnownModel | None:
    normalized = model_id.strip().lower()
    known = _KNOWN_CAPABILITIES.get(normalized)
    if known is not None:
        return known
    if "/" in normalized:
        return _KNOWN_CAPABILITIES.get(normalized.rsplit("/", 1)[-1])
    return None


def _prefer(provider_value: int | None, known_value: int | None) -> int | None:
    return provider_value if provider_value is not None else known_value


def resolve_model_capability(
    model_id: str,
    *,
    provider_supplied: ModelCapability | None = None,
) -> ModelCapability:
    """Return token limits for a model, preferring provider-advertised values.

    Provider-supplied limits win per-field; the built-in catalog fills in any
    field the provider did not advertise. Unknown models resolve to an empty
    capability so callers can fall back to their own defaults.
    """

    known = _known_capability(model_id)
    if provider_supplied is None:
        if known is None:
            return ModelCapability()
        return ModelCapability(
            context_window=known.context_window,
            max_output_tokens=known.max_output_tokens,
        )
    return ModelCapability(
        context_window=_prefer(
            provider_supplied.context_window,
            known.context_window if known is not None else None,
        ),
        max_output_tokens=_prefer(
            provider_supplied.max_output_tokens,
            known.max_output_tokens if known is not None else None,
        ),
    )
