"""Centralized OpenAI LLM client wrapper with operational logging."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


def _short_request_id() -> str:
    return uuid.uuid4().hex[:8]


def _approx_prompt_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_approx_prompt_size(item) for item in value)
    if isinstance(value, dict):
        return sum(_approx_prompt_size(v) for v in value.values())
    return len(str(value))


def _extract_prompt_size(kwargs: dict[str, Any]) -> int:
    if "input" in kwargs:
        return _approx_prompt_size(kwargs["input"])
    if "messages" in kwargs:
        return _approx_prompt_size(kwargs["messages"])
    return 0


def _extract_usage(data: dict[str, Any]) -> tuple[int | None, int | None]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None, None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens, output_tokens
    return None, None


def llm_call(feature: str, **kwargs: Any) -> dict[str, Any]:
    """Call OpenAI Responses API with consistent logging and safety controls."""
    request_id = _short_request_id()
    prompt_size = _extract_prompt_size(kwargs)

    if os.getenv("DISABLE_LLM", "").strip() == "1":
        print(
            f"[LLM BLOCKED] feature={feature} request_id={request_id} "
            f"reason=DISABLE_LLM prompt_chars={prompt_size}"
        )
        raise RuntimeError("LLM call blocked by DISABLE_LLM=1")

    api_key = str(kwargs.pop("api_key", os.getenv("OPENAI_API_KEY", ""))).strip()
    if not api_key:
        raise RuntimeError("Missing OpenAI API key")

    base_url = str(kwargs.pop("base_url", "https://api.openai.com/v1")).strip()
    timeout_sec = int(kwargs.pop("timeout_sec", 60))
    url = f"{base_url.rstrip('/')}/responses"

    print(f"[LLM START] feature={feature} request_id={request_id}")
    started_at = time.monotonic()

    req = urllib.request.Request(
        url=url,
        data=json.dumps(kwargs).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        print(
            f"[LLM ERROR] feature={feature} request_id={request_id} "
            f"latency_ms={latency_ms} status={exc.code}"
        )
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"LLM request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        print(
            f"[LLM ERROR] feature={feature} request_id={request_id} "
            f"latency_ms={latency_ms} reason={exc}"
        )
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    latency_ms = int((time.monotonic() - started_at) * 1000)
    input_tokens, output_tokens = _extract_usage(data)
    usage_log = ""
    if input_tokens is not None and output_tokens is not None:
        usage_log = f" input_tokens={input_tokens} output_tokens={output_tokens}"
    print(
        f"[LLM END] feature={feature} request_id={request_id} "
        f"latency_ms={latency_ms} prompt_chars={prompt_size}{usage_log}"
    )
    return data
