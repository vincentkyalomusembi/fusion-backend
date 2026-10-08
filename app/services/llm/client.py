"""Thin wrapper around the OpenAI chat completions API."""
import time

import httpx

from app.config import settings


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    response = None
    for attempt in range(3):
        try:
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": messages,
                },
                timeout=httpx.Timeout(60.0, connect=15.0),
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
            if response is not None and response.status_code < 500 and response.status_code != 429:
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("LLM request failed after retries")
