from __future__ import annotations

from typing import Any

from .settings import normalize_mode


def _present(mapping: dict[str, Any] | None) -> list[Any]:
    return [value for value in (mapping or {}).values() if value is not None]


def validate_reference_pack(settings: dict[str, Any], pack: dict[str, Any]) -> None:
    mode = normalize_mode(settings["workflow_mode"])
    images = _present(pack.get("ref_images"))
    videos = _present(pack.get("ref_videos"))
    video_audios = _present(pack.get("ref_video_audios"))
    audios = _present(pack.get("ref_audios"))
    first = pack.get("first_frame")
    last = pack.get("last_frame")

    if len(images) > 9:
        raise ValueError(f"Ref2VA supports at most 9 reference images; received {len(images)}")
    if len(videos) > 3:
        raise ValueError(f"Ref2VA supports at most 3 reference videos; received {len(videos)}")
    if len(video_audios) > 3:
        raise ValueError(f"Ref2VA supports at most 3 paired video audios; received {len(video_audios)}")
    if len(audios) > 3:
        raise ValueError(f"Ref2VA supports at most 3 standalone audios; received {len(audios)}")

    has_refs = bool(images or videos or video_audios or audios)
    if mode == "T2VA" and (has_refs or first is not None or last is not None):
        raise ValueError("T2VA does not accept reference media or keyframes")
    if mode == "I2VA":
        if first is None:
            raise ValueError("I2VA requires first_frame")
        if has_refs or last is not None:
            raise ValueError("I2VA accepts only first_frame")
    if mode == "FL2VA":
        if first is None or last is None:
            raise ValueError("FL2VA requires both first_frame and last_frame")
        if has_refs:
            raise ValueError("FL2VA does not accept Ref2VA reference media")
    if mode == "L2VA":
        if last is None:
            raise ValueError("L2VA requires last_frame")
        if has_refs or first is not None:
            raise ValueError("L2VA accepts only last_frame")
    if mode == "Ref2VA":
        if first is not None or last is not None:
            raise ValueError("Current official Ref2VA conditioning does not accept first_frame or last_frame")
        if video_audios and not videos:
            raise ValueError("Paired video audio was supplied without a reference video")

