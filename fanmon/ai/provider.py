"""OpenAI-compatible chat-completions provider with native tool calling.

Stdlib urllib only — no httpx/requests. The API key is resolved per call and
is never logged or written anywhere.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

from .config import resolve_api_key

TIMEOUT_S = 90
MAX_TOKENS = 4096


class ProviderError(Exception):
    """Short human-readable failure for status lines and CLI output."""


class OpenAICompatProvider:
    def __init__(self, base_url: str, model: str, key_source: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.key_source = key_source

    def chat(self, messages: list, tools: list,
             max_tokens: int = MAX_TOKENS,
             tool_choice="auto") -> dict:
        """One round-trip; returns the assistant message dict."""
        try:
            key = resolve_api_key(self.key_source)
        except Exception as e:
            raise ProviderError(f"API key: {e}")
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning_effort": "low",
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                pass
            raise ProviderError(f"HTTP {e.code} {detail}".strip())
        except Exception as e:
            raise ProviderError(str(e) or type(e).__name__)
        try:
            return data["choices"][0]["message"]
        except Exception:
            raise ProviderError("malformed response (no choices[0].message)")
