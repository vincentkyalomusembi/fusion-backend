"""Thin wrapper around the Gemini generateContent REST API."""
import random
import time

import httpx

from app.config import settings

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_BACKOFF = [5, 15, 30, 60]


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key or "",
    }


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_turns = [m for m in messages if m["role"] != "system"]
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in user_turns
    ]
    body: dict = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}

    url = f"{_BASE}/{settings.gemini_model}:generateContent"
    response = None
    for attempt in range(len(_BACKOFF) + 1):
        try:
            response = httpx.post(url, headers=_headers(), json=body, timeout=httpx.Timeout(60.0, connect=15.0))
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except httpx.HTTPStatusError:
            if response is None:
                raise
            if response.status_code not in (429, 500, 502, 503, 504):
                raise
            if attempt >= len(_BACKOFF):
                raise
            time.sleep(_BACKOFF[attempt] + random.uniform(0, 1))
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt >= len(_BACKOFF):
                raise
            time.sleep(_BACKOFF[attempt] + random.uniform(0, 1))
    raise RuntimeError("Gemini request failed after retries")
