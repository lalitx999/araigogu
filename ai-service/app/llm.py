"""Thin wrapper around the OpenAI chat API. Returns None instead of raising."""
import asyncio
import logging

from openai import AsyncOpenAI

from .config import Settings

log = logging.getLogger("ai-service.llm")


class LLM:
    def __init__(self, settings: Settings):
        self.model = settings.openai_model
        self.timeout = settings.request_timeout
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self._client = (
            AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.request_timeout)
            if settings.openai_api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str | None:
        if not self._client:
            return None
        kwargs: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        try:
            async with self._sem:
                resp = await self._client.chat.completions.create(**kwargs)
        except Exception:  # network, auth, rate limit... never leak to caller
            log.exception("OpenAI call failed")
            return None
        return resp.choices[0].message.content
