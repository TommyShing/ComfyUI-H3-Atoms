from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .profiles import APIProfile


Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


@dataclass(frozen=True)
class CompletionResult:
    content: str
    finish_reason: str | None
    usage: dict[str, Any]
    raw: dict[str, Any]

    @property
    def truncated(self) -> bool:
        value = (self.finish_reason or "").lower()
        return value in {"length", "max_tokens", "max_output_tokens", "incomplete"}


def chat_completions_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("API base URL cannot be empty")
    if value.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


def build_payload(
    profile: APIProfile,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": profile.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        profile.token_parameter: profile.max_tokens,
    }
    if profile.reasoning_effort != "disabled":
        payload["reasoning_effort"] = profile.reasoning_effort
    return payload


def _default_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def parse_response(data: dict[str, Any]) -> CompletionResult:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Compatible response has no choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("Compatible response choice is not an object")
    message = choice.get("message") or {}
    content = _content_to_text(message.get("content")).strip()
    if not content:
        raise ValueError("Compatible response has no final message.content")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return CompletionResult(content, choice.get("finish_reason"), usage, data)


def request_chat_completion(
    profile: APIProfile,
    api_key: str,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
    transport: Transport | None = None,
) -> CompletionResult:
    profile.validate()
    if not profile.model.strip():
        raise ValueError("API model cannot be empty")
    payload = build_payload(profile, system_prompt, user_content)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, response_body = (transport or _default_transport)(
        chat_completions_url(profile.base_url), headers, body, profile.timeout_seconds
    )
    text = response_body.decode("utf-8", errors="replace")
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status}: {text[:4000]}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Compatible endpoint returned invalid JSON: {text[:1000]}") from exc
    if not isinstance(data, dict):
        raise ValueError("Compatible endpoint returned a non-object JSON response")
    return parse_response(data)

