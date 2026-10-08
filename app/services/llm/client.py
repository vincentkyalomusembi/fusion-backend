"""Thin wrapper around the OpenAI chat completions API."""
import time

import httpx

from app.config import settings

_RETRIES = 4
_BACKOFF = [5, 15, 30, 60]  # seconds to wait after each 429 / 5xx


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    response = None
    for attempt in range(_RETRIES):
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
        except httpx.HTTPStatusError:
            if response is None:
                raise
            status = response.status_code
            # 4xx that are not rate-limit errors are not retryable
            if status < 500 and status != 429:
                raise
            if attempt == _RETRIES - 1:
                raise
            # Respect Retry-After header if OpenAI sends one, else use backoff table
            retry_after = response.headers.get("retry-after")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else _BACKOFF[attempt]
            time.sleep(wait)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == _RETRIES - 1:
                raise
            time.sleep(_BACKOFF[attempt])
    raise RuntimeError("LLM request failed after retries")
