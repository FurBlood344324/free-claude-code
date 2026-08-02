import pytest

from free_claude_code.application.model_metadata import ModelCapability
from free_claude_code.providers.model_listing import (
    ModelListResponseError,
    extract_openai_model_infos,
    extract_tool_capable_model_infos,
    model_capability_from_item,
)


def test_model_capability_from_item_reads_openrouter_fields():
    item = {
        "id": "anthropic/claude-opus-4-5",
        "context_length": 200000,
        "top_provider": {"max_completion_tokens": 64000},
    }

    assert model_capability_from_item(item) == ModelCapability(
        context_window=200000, max_output_tokens=64000
    )


def test_model_capability_from_item_supports_flat_fields():
    item = {
        "id": "deepseek/deepseek-chat",
        "context_window": 128000,
        "max_tokens": 8192,
    }

    assert model_capability_from_item(item) == ModelCapability(
        context_window=128000, max_output_tokens=8192
    )


def test_model_capability_from_item_ignores_missing_or_invalid_values():
    item = {
        "id": "deepseek/deepseek-chat",
        "context_length": "200000",
        "max_tokens": -5,
    }

    assert model_capability_from_item(item) == ModelCapability()


def test_extract_openai_model_infos_carries_capabilities():
    payload = {
        "data": [
            {
                "id": "deepseek/deepseek-chat",
                "context_length": 128000,
                "top_provider": {"max_completion_tokens": 8192},
            },
            {"id": "meta/llama-3.3", "context_length": 128000},
        ]
    }

    infos = extract_openai_model_infos(payload, provider_name="open_router")

    by_id = {info.model_id: info for info in infos}
    assert by_id["deepseek/deepseek-chat"].context_window == 128000
    assert by_id["deepseek/deepseek-chat"].max_output_tokens == 8192
    assert by_id["meta/llama-3.3"].context_window == 128000
    assert by_id["meta/llama-3.3"].max_output_tokens is None


def test_extract_openai_model_infos_without_capability_fields_is_still_valid():
    payload = {"data": [{"id": "deepseek/deepseek-chat"}, {"id": "mini-max/m2.5"}]}

    infos = extract_openai_model_infos(payload, provider_name="nvidia_nim")

    assert {info.model_id for info in infos} == {
        "deepseek/deepseek-chat",
        "mini-max/m2.5",
    }
    assert all(info.context_window is None for info in infos)


def test_extract_tool_capable_model_infos_carries_capabilities():
    payload = {
        "data": [
            {
                "id": "DeepSeek-V4-Pro",
                "supported_parameters": ["tools", "tool_choice", "reasoning"],
                "context_length": 1000000,
                "top_provider": {"max_completion_tokens": 384000},
            },
            {
                "id": "MiniMax-M2.7",
                "supported_parameters": ["tools"],
                "context_length": 204800,
            },
            {
                "id": "No-Tools",
                "supported_parameters": ["reasoning"],
                "context_length": 1000000,
            },
        ]
    }

    infos = extract_tool_capable_model_infos(payload, provider_name="wafer")

    by_id = {info.model_id: info for info in infos}
    assert by_id["DeepSeek-V4-Pro"].supports_thinking is True
    assert by_id["DeepSeek-V4-Pro"].context_window == 1000000
    assert by_id["DeepSeek-V4-Pro"].max_output_tokens == 384000
    assert by_id["MiniMax-M2.7"].supports_thinking is False
    assert by_id["MiniMax-M2.7"].context_window == 204800
    assert "No-Tools" not in by_id


def test_extract_openai_model_infos_rejects_malformed_payload():
    with pytest.raises(ModelListResponseError):
        extract_openai_model_infos({"data": [{"id": 42}]}, provider_name="wafer")
