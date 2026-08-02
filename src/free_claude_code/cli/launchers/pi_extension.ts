import type { ExtensionAPI, ProviderModelConfig } from "@earendil-works/pi-coding-agent";

const API_KEY_ENV = "FCC_PI_API_KEY";
const BASE_URL_ENV = "FCC_PI_BASE_URL";
const CATALOG_TIMEOUT_MS = 3000;
const DEFAULT_CONTEXT_WINDOW = 128000;
const DEFAULT_MAX_TOKENS = 16384;
const NORMAL_MODEL_PREFIX = "anthropic/";
const NO_THINKING_MODEL_PREFIX = "claude-3-freecc-no-thinking/";

interface CatalogEntry {
	id: string;
	contextWindow?: number;
	maxTokens?: number;
}

function requireEnvironment(name: string): string {
	const value = process.env[name]?.trim();
	if (!value) {
		throw new Error(`Missing required ${name} environment variable.`);
	}
	return value;
}

function normalizeBaseUrl(value: string): string {
	let url: URL;
	try {
		url = new URL(value);
	} catch {
		throw new Error(`${BASE_URL_ENV} is not a valid URL.`);
	}
	if (url.protocol !== "http:" && url.protocol !== "https:") {
		throw new Error(`${BASE_URL_ENV} must use http or https.`);
	}
	url.search = "";
	url.hash = "";
	return url.toString().replace(/\/+$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function positiveInt(value: unknown): number | undefined {
	return typeof value === "number" && Number.isSafeInteger(value) && value > 0
		? value
		: undefined;
}

function catalogEntryCapability(entry: Record<string, unknown>): {
	contextWindow?: number;
	maxTokens?: number;
} {
	return {
		contextWindow: positiveInt(entry.context_window),
		maxTokens: positiveInt(entry.max_output_tokens),
	};
}

function catalogEntries(payload: unknown): CatalogEntry[] {
	if (!isRecord(payload) || payload.object !== "list" || !Array.isArray(payload.data)) {
		throw new Error("FCC model catalog returned an invalid response shape.");
	}

	const entries: CatalogEntry[] = [];
	for (const raw of payload.data) {
		if (!isRecord(raw) || typeof raw.id !== "string") continue;
		const id = raw.id.trim();
		if (!id) continue;
		const capability = catalogEntryCapability(raw);
		entries.push({ id, ...capability });
	}
	return entries;
}

function providerModelRef(id: string, prefix: string): string | undefined {
	if (!id.startsWith(prefix)) return undefined;
	const parts = id.slice(prefix.length).split("/");
	if (parts.length < 2 || parts.some((part) => !part)) return undefined;
	return parts.join("/");
}

function modelDefinition(
	providerModel: string,
	reasoning: boolean,
	capability: { contextWindow?: number; maxTokens?: number } = {},
): ProviderModelConfig {
	return {
		id: providerModel,
		name: providerModel,
		reasoning,
		input: ["text"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: capability.contextWindow ?? DEFAULT_CONTEXT_WINDOW,
		maxTokens: capability.maxTokens ?? DEFAULT_MAX_TOKENS,
	};
}

export function projectFccModels(payload: unknown): ProviderModelConfig[] {
	const entries = catalogEntries(payload);
	const normalModels = new Set<string>();
	for (const entry of entries) {
		const providerModel = providerModelRef(entry.id, NORMAL_MODEL_PREFIX);
		if (providerModel) normalModels.add(providerModel);
	}

	const models: ProviderModelConfig[] = [];
	const seen = new Set<string>();
	for (const entry of entries) {
		const normalModel = providerModelRef(entry.id, NORMAL_MODEL_PREFIX);
		if (normalModel) {
			if (!seen.has(normalModel)) {
				seen.add(normalModel);
				models.push(modelDefinition(normalModel, true, entry));
			}
			continue;
		}

		const noThinkingModel = providerModelRef(entry.id, NO_THINKING_MODEL_PREFIX);
		if (!noThinkingModel || normalModels.has(noThinkingModel) || seen.has(noThinkingModel)) continue;
		seen.add(noThinkingModel);
		models.push(modelDefinition(noThinkingModel, false, entry));
	}

	if (models.length === 0) {
		throw new Error("FCC model catalog contains no routable provider models.");
	}
	return models;
}

function requestIdSuffix(response: Response): string {
	const requestId = response.headers.get("request-id") ?? response.headers.get("x-request-id");
	return requestId ? ` (request ${requestId})` : "";
}

async function fetchFccModels(baseUrl: string, apiKey: string): Promise<ProviderModelConfig[]> {
	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), CATALOG_TIMEOUT_MS);
	try {
		let response: Response;
		try {
			response = await fetch(`${baseUrl}/v1/models`, {
				headers: { Authorization: `Bearer ${apiKey}` },
				signal: controller.signal,
			});
		} catch (error) {
			if (error instanceof Error && error.name === "AbortError") {
				throw new Error(`FCC model catalog timed out after ${CATALOG_TIMEOUT_MS}ms.`);
			}
			const message = error instanceof Error ? error.message : String(error);
			throw new Error(`Could not reach the FCC model catalog: ${message}`);
		}

		if (!response.ok) {
			throw new Error(`FCC model catalog returned HTTP ${response.status}${requestIdSuffix(response)}.`);
		}

		let payload: unknown;
		try {
			payload = await response.json();
		} catch (error) {
			if (error instanceof Error && error.name === "AbortError") {
				throw new Error(`FCC model catalog timed out after ${CATALOG_TIMEOUT_MS}ms.`);
			}
			throw new Error(`FCC model catalog returned invalid JSON${requestIdSuffix(response)}.`);
		}
		return projectFccModels(payload);
	} finally {
		clearTimeout(timeout);
	}
}

export default async function freeClaudeCode(pi: ExtensionAPI): Promise<void> {
	const baseUrl = normalizeBaseUrl(requireEnvironment(BASE_URL_ENV));
	const apiKey = requireEnvironment(API_KEY_ENV);
	const models = await fetchFccModels(baseUrl, apiKey);

	pi.registerProvider("free-claude-code", {
		name: "Free Claude Code",
		baseUrl,
		apiKey: `$${API_KEY_ENV}`,
		authHeader: true,
		api: "anthropic-messages",
		models,
	});
}
