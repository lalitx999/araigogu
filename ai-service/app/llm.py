"""Multi-provider wrapper around Gemini, Groq, DeepSeek, and OpenAI chat APIs.
Returns None on failure instead of raising.
"""
import asyncio
import logging

from openai import AsyncOpenAI

from .config import Settings

log = logging.getLogger("ai-service.llm")


class LLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.openai_model
        self.timeout = settings.request_timeout
        self._sem = asyncio.Semaphore(settings.max_concurrency)

        # Standard OpenAI client (backwards compatible for tests & fallback)
        self._client = (
            AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.request_timeout)
            if settings.openai_api_key
            else None
        )

        # Multi-provider clients dictionary
        self._clients: dict[str, tuple[AsyncOpenAI, str]] = {}

        if settings.gemini_api_key:
            self._clients["gemini"] = (
                AsyncOpenAI(
                    api_key=settings.gemini_api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    timeout=settings.request_timeout,
                ),
                settings.gemini_model or "gemini-2.5-flash",
            )

        if settings.groq_api_key:
            self._clients["groq"] = (
                AsyncOpenAI(
                    api_key=settings.groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=settings.request_timeout,
                ),
                settings.groq_model or "llama-3.3-70b-versatile",
            )

        if settings.deepseek_api_key:
            self._clients["deepseek"] = (
                AsyncOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url="https://api.deepseek.com/v1",
                    timeout=settings.request_timeout,
                ),
                settings.deepseek_model or "deepseek-chat",
            )

        if self._client:
            self._clients["openai"] = (self._client, settings.openai_model or "gpt-4o-mini")

    @property
    def available(self) -> bool:
        return self._client is not None or len(self._clients) > 0

    def get_configured_providers(self) -> list[str]:
        providers = list(self._clients.keys())
        if self._client and "openai" not in providers:
            providers.append("openai")
        return providers

    def _resolve_client(
        self, provider: str, custom_model: str = "", has_images: bool = False
    ) -> tuple[AsyncOpenAI | None, str, str]:
        provider = (provider or "").lower().strip()

        # If tests injected a custom self._client, use it directly
        if self._client and type(self._client).__name__ != "AsyncOpenAI":
            return self._client, "custom", custom_model or self.model

        # If images are attached, ALWAYS route directly to Google Gemini 2.5 Flash (Vision)
        if has_images:
            if "gemini" in self._clients:
                client, default_model = self._clients["gemini"]
                chosen_gemini_model = (
                    custom_model if (custom_model and "gemini" in custom_model) else default_model
                )
                return client, "gemini", chosen_gemini_model
            if "openai" in self._clients:
                client, default_model = self._clients["openai"]
                return client, "openai", default_model
            if self._client:
                return self._client, "openai", self.model

        # Normal text chat routing: prefer Groq (fast) & DeepSeek (reasoning)
        if provider in ("groq", "deepseek") and provider in self._clients:
            client, default_model = self._clients[provider]
            return client, provider, custom_model or default_model

        if provider in self._clients:
            client, default_model = self._clients[provider]
            return client, provider, custom_model or default_model

        # Fallback hierarchy for text chat: groq -> deepseek -> gemini -> openai -> self._client
        for fallback in ("groq", "deepseek", "gemini", "openai"):
            if fallback in self._clients:
                client, default_model = self._clients[fallback]
                return client, fallback, default_model

        if self._client:
            return self._client, "openai", custom_model or self.model

        return None, provider or "none", custom_model or "none"

    async def complete(
        self,
        messages: list[dict],
        *,
        provider: str = "groq",
        custom_model: str = "",
        has_images: bool = False,
        temperature: float = 0.3,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str | None:
        content, _, _ = await self.complete_chat(
            messages,
            provider=provider,
            custom_model=custom_model,
            has_images=has_images,
            temperature=temperature,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )
        return content

    async def complete_chat(
        self,
        messages: list[dict],
        *,
        provider: str = "groq",
        custom_model: str = "",
        has_images: bool = False,
        temperature: float = 0.3,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> tuple[str | None, str, str]:
        client, chosen_provider, model_name = self._resolve_client(
            provider, custom_model=custom_model, has_images=has_images
        )
        if not client:
            return None, chosen_provider, model_name

        kwargs: dict = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        try:
            async with self._sem:
                resp = await client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content, chosen_provider, model_name
        except Exception:
            log.exception("LLM call failed for provider=%s model=%s", chosen_provider, model_name)
            return None, chosen_provider, model_name
