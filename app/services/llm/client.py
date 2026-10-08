"""Thin wrapper around the Gemini generateContent REST API."""
import time

import httpx

from app.config import settings

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_BACKOFF = [5, 15, 30, 60]


def _gemini_url(model: str) -> str:
    return f"{_BASE}/{model}:generateContent?key={settings.gemini_api_key}"


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    # Convert OpenAI-style messages to Gemini contents format.
    # System message is passed via systemInstruction.
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

    response = None
    for attempt in range(len(_BACKOFF) + 1):
        try:
            response = httpx.post(
                _gemini_url(settings.gemini_model),
                json=body,
                timeout=httpx.Timeout(60.0, connect=15.0),
            )
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except httpx.HTTPStatusError:
            if response is None:
                raise
            status = response.status_code
            if status not in (429, 500, 502, 503, 504):
                raise
            if attempt >= len(_BACKOFF):
                raise
            retry_after = response.headers.get("retry-after", "")
            wait = float(retry_after) if retry_after.isdigit() else _BACKOFF[attempt]
            time.sleep(wait)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt >= len(_BACKOFF):
                raise
            time.sleep(_BACKOFF[attempt])
    raise RuntimeError("Gemini request failed after retries")
