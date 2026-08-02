"""Application-owned model metadata."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Token limits a provider advertises for one model, when known."""

    context_window: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderModelInfo:
    """Provider model metadata used to shape the application model catalog."""

    model_id: str
    supports_thinking: bool | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None

    @property
    def capability(self) -> ModelCapability:
        """Return the provider-advertised token limits as one capability value."""
        return ModelCapability(
            context_window=self.context_window,
            max_output_tokens=self.max_output_tokens,
        )


@dataclass(frozen=True, slots=True)
class ProviderModelRefreshResult:
    """Per-provider outcome of one model-catalog refresh."""

    refreshed_provider_ids: tuple[str, ...] = ()
    failed_provider_ids: tuple[str, ...] = ()
