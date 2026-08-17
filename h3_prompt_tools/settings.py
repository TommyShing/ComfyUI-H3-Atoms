from __future__ import annotations

import math
from typing import Any


FPS = 24
VALID_MODES = ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA")
WORKFLOW_MODE_OPTIONS = ("T2VA", "I2VA", "FL2VA", "L2VA", "FULL_REFERENCE")
MAX_FRAME_COUNT = 3600
MAX_DURATION_SECONDS = MAX_FRAME_COUNT / FPS
MODE_ALIASES = {
    "FULL_REFERENCE": "Ref2VA",
    "FULL REFERENCE": "Ref2VA",
    "REF2VA": "Ref2VA",
}


def normalize_mode(mode: str) -> str:
    value = str(mode).strip()
    normalized = MODE_ALIASES.get(value.upper(), value.upper())
    if normalized == "REF2VA":
        normalized = "Ref2VA"
    if normalized not in VALID_MODES:
        raise ValueError(f"Unsupported H3 workflow mode: {mode!r}")
    return normalized


def align_frame_count(frame_count: int) -> int:
    value = max(5, int(frame_count))
    while value % 17 != 5:
        value += 1
    return value


def build_generation_settings(
    workflow_mode: str,
    width: int,
    height: int,
    duration: float,
) -> dict[str, Any]:
    mode = normalize_mode(workflow_mode)
    width = int(width)
    height = int(height)
    duration = float(duration)
    if width < 32 or height < 32:
        raise ValueError("width and height must both be at least 32")
    if duration <= 0:
        raise ValueError("duration must be greater than zero")

    if duration > MAX_DURATION_SECONDS:
        raise ValueError(
            f"duration {duration:.3f}s exceeds the official H3 requested-length "
            f"budget of {MAX_FRAME_COUNT} frames ({MAX_DURATION_SECONDS:.3f}s)"
        )
    requested_frames = math.ceil(duration * FPS)
    frame_count = align_frame_count(requested_frames)
    return {
        "workflow_mode": mode,
        "width": width,
        "height": height,
        "requested_duration": duration,
        "fps": FPS,
        "frame_count": frame_count,
        "actual_duration": frame_count / FPS,
    }

