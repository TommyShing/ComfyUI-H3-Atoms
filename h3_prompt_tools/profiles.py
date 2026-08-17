from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


API_FORMATS = ("completions", "responses", "gemini_native")
TOKEN_PARAMETERS = ("max_completion_tokens", "max_tokens", "max_output_tokens")
REASONING_EFFORTS = ("disabled", "none", "minimal", "low", "medium", "high")


@dataclass(frozen=True)
class APIProfile:
    name: str
    base_url: str
    model: str
    api_key_env: str = ""
    api_format: str = "completions"
    token_parameter: str = "max_completion_tokens"
    max_tokens: int = 8192
    reasoning_effort: str = "disabled"
    timeout_seconds: float = 120.0
    send_ref_images: bool = True
    send_ref_videos: bool = True
    send_ref_audio: bool = False
    send_keyframes: bool = True
    direct_video: bool = False
    jpeg_quality: int = 90
    sampled_video_frames: int = 3

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "APIProfile":
        profile = cls(**data)
        profile.validate()
        return profile

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("profile name cannot be empty")
        if self.api_format not in API_FORMATS:
            raise ValueError(f"Unsupported API format: {self.api_format}")
        if self.token_parameter not in TOKEN_PARAMETERS:
            raise ValueError(f"Unsupported token parameter: {self.token_parameter}")
        if self.reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(f"Unsupported reasoning effort: {self.reasoning_effort}")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if not 1 <= self.sampled_video_frames <= 12:
            raise ValueError("sampled_video_frames must be between 1 and 12")

    def public_dict(self, has_session_key: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["has_api_key"] = bool(has_session_key or (self.api_key_env and os.getenv(self.api_key_env)))
        return data


class ProfileStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._session_keys: dict[str, str] = {}

    def _load_raw(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("profiles.json must contain an object")
        return data

    def list(self) -> list[APIProfile]:
        with self._lock:
            return [APIProfile.from_mapping(value) for _, value in sorted(self._load_raw().items())]

    def names(self) -> list[str]:
        return [profile.name for profile in self.list()]

    def get(self, name: str) -> APIProfile:
        with self._lock:
            raw = self._load_raw()
            if name not in raw:
                raise KeyError(f"Unknown API profile: {name}")
            return APIProfile.from_mapping(raw[name])

    def save(self, profile: APIProfile, api_key: str | None = None) -> None:
        profile.validate()
        with self._lock:
            raw = self._load_raw()
            raw[profile.name] = asdict(profile)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(self.path)
            if api_key:
                self._session_keys[profile.name] = api_key.strip()

    def delete(self, name: str) -> None:
        with self._lock:
            raw = self._load_raw()
            raw.pop(name, None)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(self.path)
            self._session_keys.pop(name, None)

    def resolve_api_key(self, profile: APIProfile) -> str:
        with self._lock:
            session_key = self._session_keys.get(profile.name, "")
        if session_key:
            return session_key
        if profile.api_key_env:
            env_key = os.getenv(profile.api_key_env, "").strip()
            if env_key:
                return env_key
        raise ValueError(
            f"API profile {profile.name!r} has no session key and environment variable "
            f"{profile.api_key_env!r} is not set"
        )

    def public_list(self) -> list[dict[str, Any]]:
        with self._lock:
            keys = set(self._session_keys)
        return [profile.public_dict(profile.name in keys) for profile in self.list()]

