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


def responses_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("API base URL cannot be empty")
    if value.endswith("/responses"):
        return value
    return value + "/responses"


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
        payload["reasoning"] = {"effort": profile.reasoning_effort}
    return payload


def _default_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def _responses_content(content: str | list[dict[str, Any]]) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return content
    parts: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            parts.append({"type": "input_text", "text": item})
        elif isinstance(item, dict) and item.get("type") == "text":
            parts.append({"type": "input_text", "text": item["text"]})
        elif isinstance(item, dict) and item.get("type") == "image_url":
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                parts.append({"type": "input_image", "image_url": image_url.get("url")})
        else:
            parts.append(item)
    return parts


def build_responses_payload(
    profile: APIProfile,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": profile.model,
        "instructions": system_prompt,
        "input": [{"role": "user", "content": _responses_content(user_content)}],
        "max_output_tokens": profile.max_tokens,
    }
    if profile.reasoning_effort != "disabled":
        payload["reasoning"] = {"effort": profile.reasoning_effort}
    return payload


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


def parse_responses_response(data: dict[str, Any]) -> CompletionResult:
    chunks: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
    content = "".join(chunks).strip()
    if not content:
        content = str(data.get("output_text") or "").strip()
    if not content:
        raise ValueError("Responses API response has no output text")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    status = data.get("status")
    if status == "completed":
        finish_reason = "stop"
    elif status == "incomplete":
        details = data.get("incomplete_details") or {}
        finish_reason = details.get("reason") if isinstance(details, dict) else None
        finish_reason = finish_reason or "incomplete"
    else:
        finish_reason = status
    return CompletionResult(content, finish_reason, usage, data)


def request_responses_completion(
    profile: APIProfile,
    api_key: str,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
    transport: Transport | None = None,
) -> CompletionResult:
    profile.validate()
    if not profile.model.strip():
        raise ValueError("API model cannot be empty")
    payload = build_responses_payload(profile, system_prompt, user_content)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, response_body = (transport or _default_transport)(
        responses_url(profile.base_url), headers, body, profile.timeout_seconds
    )
    text = response_body.decode("utf-8", errors="replace")
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status}: {text[:4000]}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Responses endpoint returned invalid JSON: {text[:1000]}") from exc
    if not isinstance(data, dict):
        raise ValueError("Responses endpoint returned a non-object JSON response")
    return parse_responses_response(data)


def gemini_generate_content_url(base_url: str, model: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("API base URL cannot be empty")
    if value.endswith(":generateContent"):
        return value
    return value + f"/models/{model}:generateContent"


def _gemini_parts(user_content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(user_content, str):
        return [{"text": user_content}]
    parts: list[dict[str, Any]] = []
    for item in user_content:
        if isinstance(item, str):
            parts.append({"text": item})
        elif not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append({"text": item.get("text", "")})
        elif item.get("type") == "image_url":
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            if not isinstance(image_url, str):
                continue
            if image_url.startswith("data:"):
                try:
                    header, payload = image_url.split(",", 1)
                    mime = header[5:].split(";")[0] or "image/jpeg"
                except ValueError as exc:
                    raise ValueError("Invalid Gemini inline image data URL") from exc
                parts.append({"inlineData": {"mimeType": mime, "data": payload}})
            else:
                parts.append({"fileData": {"mimeType": "image/jpeg", "fileUri": image_url}})
    return parts


def build_gemini_payload(
    profile: APIProfile,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": _gemini_parts(user_content)}],
        "generationConfig": {"maxOutputTokens": profile.max_tokens},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    return payload


def parse_gemini_response(data: dict[str, Any]) -> CompletionResult:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        feedback = data.get("promptFeedback") or {}
        reason = feedback.get("blockReason") if isinstance(feedback, dict) else None
        if reason:
            raise ValueError(f"Gemini API blocked the request: {reason}")
        raise ValueError("Gemini API returned no candidates")
    chunks: list[str] = []
    finish_reason = None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        finish_reason = candidate.get("finishReason") or finish_reason
        content = candidate.get("content") or {}
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if not chunks:
        raise ValueError("Gemini API response has no text")
    usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
    return CompletionResult("\n".join(chunks).strip(), finish_reason, usage, data)


def request_gemini_native(
    profile: APIProfile,
    api_key: str,
    system_prompt: str,
    user_content: str | list[dict[str, Any]],
    transport: Transport | None = None,
) -> CompletionResult:
    profile.validate()
    if not profile.model.strip():
        raise ValueError("API model cannot be empty")
    payload = build_gemini_payload(profile, system_prompt, user_content)
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, response_body = (transport or _default_transport)(
        gemini_generate_content_url(profile.base_url, profile.model),
        headers,
        body,
        profile.timeout_seconds,
    )
    text = response_body.decode("utf-8", errors="replace")
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status}: {text[:4000]}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini endpoint returned invalid JSON: {text[:1000]}") from exc
    if not isinstance(data, dict):
        raise ValueError("Gemini endpoint returned a non-object JSON response")
    return parse_gemini_response(data)



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

