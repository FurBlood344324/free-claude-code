from free_claude_code.application.model_capabilities import resolve_model_capability
from free_claude_code.application.model_metadata import ModelCapability


def test_unknown_model_resolves_to_empty_capability():
    capability = resolve_model_capability("mystery-model-9000")

    assert capability == ModelCapability()


def test_known_model_uses_builtin_catalog():
    capability = resolve_model_capability("deepseek-v4-flash")

    assert capability == ModelCapability(
        context_window=1000000, max_output_tokens=384000
    )


def test_builtin_lookup_is_case_insensitive_and_prefix_tolerant():
    assert resolve_model_capability("DEEPSEEK-V4-PRO") == ModelCapability(
        context_window=1000000, max_output_tokens=384000
    )
    assert resolve_model_capability("anthropic/claude-opus-4-5") == ModelCapability(
        context_window=200000, max_output_tokens=64000
    )


def test_provider_supplied_values_win_over_builtin():
    capability = resolve_model_capability(
        "deepseek-v4-flash",
        provider_supplied=ModelCapability(
            context_window=262144, max_output_tokens=65536
        ),
    )

    assert capability == ModelCapability(context_window=262144, max_output_tokens=65536)


def test_provider_supplied_values_fill_missing_builtin_fields():
    capability = resolve_model_capability(
        "deepseek-v4-flash",
        provider_supplied=ModelCapability(
            context_window=500000, max_output_tokens=None
        ),
    )

    assert capability == ModelCapability(
        context_window=500000, max_output_tokens=384000
    )


def test_provider_supplied_empty_capability_falls_back_to_builtin():
    capability = resolve_model_capability(
        "deepseek-v4-pro", provider_supplied=ModelCapability()
    )

    assert capability == ModelCapability(
        context_window=1000000, max_output_tokens=384000
    )


def test_provider_supplied_for_unknown_model_is_kept_as_is():
    capability = resolve_model_capability(
        "mystery-model-9000",
        provider_supplied=ModelCapability(
            context_window=200000, max_output_tokens=16000
        ),
    )

    assert capability == ModelCapability(context_window=200000, max_output_tokens=16000)


def test_claude_compatibility_aliases_have_builtin_capabilities():
    assert resolve_model_capability("claude-sonnet-4-20250514") == ModelCapability(
        context_window=200000, max_output_tokens=64000
    )
    assert resolve_model_capability("claude-opus-4-20250514") == ModelCapability(
        context_window=200000, max_output_tokens=32000
    )
    assert resolve_model_capability("claude-fable-5") == ModelCapability(
        context_window=1000000, max_output_tokens=128000
    )
