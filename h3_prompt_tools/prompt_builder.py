from __future__ import annotations

from typing import Any

from .media import parse_video_timestamps, sample_video_frames, tensor_to_jpeg_data_url
from .profiles import APIProfile
from .settings import FPS, normalize_mode


def _present(mapping: dict[str, Any] | None) -> list[tuple[str, Any]]:
    return [(name, value) for name, value in (mapping or {}).items() if value is not None]


def iter_reference_items(pack: dict[str, Any]) -> list[dict[str, Any]]:
    images = _present(pack.get("ref_images"))
    videos = _present(pack.get("ref_videos"))
    video_audios = dict(pack.get("ref_video_audios") or {})
    audios = _present(pack.get("ref_audios"))

    audio_by_video_suffix: dict[str, Any] = {}
    for name, value in video_audios.items():
        if value is not None:
            audio_by_video_suffix[name.rsplit("_", 1)[-1]] = value

    items: list[dict[str, Any]] = []
    picture_number = 0
    for source_name, image in images:
        picture_number += 1
        items.append({
            "kind": "image",
            "key": f"ref_image_{picture_number}",
            "source_name": source_name,
            "alias": f"<Picture {picture_number}>",
            "value": image,
        })

    video_number = 0
    audio_number = 0
    for source_name, video in videos:
        video_number += 1
        suffix = source_name.rsplit("_", 1)[-1]
        soundtrack = audio_by_video_suffix.get(suffix)
        if soundtrack is not None:
            audio_number += 1
            items.append({
                "kind": "audio",
                "key": f"ref_video_audio_{video_number}",
                "source_name": source_name,
                "alias": f"<Audio {audio_number}>",
                "value": soundtrack,
                "paired_with": f"ref_video_{video_number}",
            })
        items.append({
            "kind": "video",
            "key": f"ref_video_{video_number}",
            "source_name": source_name,
            "alias": f"<Video {video_number}>",
            "video_number": video_number,
            "value": video,
        })

    for source_name, audio in audios:
        audio_number += 1
        items.append({
            "kind": "audio",
            "key": f"ref_audio_{audio_number}",
            "source_name": source_name,
            "alias": f"<Audio {audio_number}>",
            "value": audio,
        })
    return items


def _keyframe_lines(pack: dict[str, Any], mode: str) -> list[str]:
    first = pack.get("first_frame")
    last = pack.get("last_frame")
    lines: list[str] = []
    if mode in {"I2VA", "FL2VA"} and first is not None:
        lines.append("- first_frame: target video starts from this supplied keyframe")
    if mode in {"FL2VA", "L2VA"} and last is not None:
        lines.append("- last_frame: target video ends at this supplied keyframe")
    return lines


def build_user_text(user_prompt: str, pack: dict[str, Any], settings: dict[str, Any]) -> str:
    mode = normalize_mode(settings["workflow_mode"])
    sections = [user_prompt.strip()]
    manifest_lines: list[str] = []

    if mode == "Ref2VA":
        for item in iter_reference_items(pack):
            detail = f" ({item['source_name']})" if item.get("source_name") else ""
            manifest_lines.append(f"- {item['alias']} = {item['key']}{detail}")
    else:
        manifest_lines.extend(_keyframe_lines(pack, mode))

    if manifest_lines:
        sections.append("Media manifest (stable aliases):\n" + "\n".join(manifest_lines))
    return "\n\n".join(section for section in sections if section).strip()


def build_system_prompt(rules: str, settings: dict[str, Any]) -> str:
    mode = normalize_mode(settings["workflow_mode"])
    lines = [
        rules.strip(),
        "Machine facts:",
        f"- Workflow mode: {mode}",
        f"- Width x height: {int(settings['width'])} x {int(settings['height'])}",
        f"- Requested duration: {float(settings['requested_duration']):.3f}s",
        f"- Frame count: {int(settings['frame_count'])}",
        f"- Actual duration: {float(settings['actual_duration']):.3f}s",
    ]
    return "\n\n".join(lines).strip() + "\n"


def _add_image_part(parts: list[dict[str, Any]], label: str, image: Any, quality: int) -> None:
    parts.append({"type": "text", "text": label})
    parts.append({"type": "image_url", "image_url": {"url": tensor_to_jpeg_data_url(image, quality=quality)}})


def _video_parts_for_item(
    item: dict[str, Any],
    user_prompt: str,
    profile: APIProfile,
) -> list[dict[str, Any]]:
    timestamps = parse_video_timestamps(user_prompt).get(item["video_number"], [])
    frames = sample_video_frames(
        item["value"],
        count=profile.sampled_video_frames,
        timestamps=timestamps,
        fps=FPS,
    )
    parts: list[dict[str, Any]] = []
    for frame, seconds in frames:
        _add_image_part(
            parts,
            f"{item['alias']} frame t={seconds:.3f}s",
            frame,
            profile.jpeg_quality,
        )
    return parts


def build_user_content(
    user_prompt: str,
    pack: dict[str, Any],
    settings: dict[str, Any],
    profile: APIProfile,
) -> list[dict[str, Any]]:
    mode = normalize_mode(settings["workflow_mode"])
    text = build_user_text(user_prompt, pack, settings)
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]

    if profile.api_format != "gemini_native" and profile.direct_video and _present(pack.get("ref_videos")):
        raise ValueError("direct_video requires api_format=gemini_native and the Gemini Files API adapter")

    if profile.api_format != "gemini_native" and profile.send_ref_audio and any(item["kind"] == "audio" for item in iter_reference_items(pack)):
        raise ValueError("send_ref_audio requires api_format=gemini_native and the Gemini Files API adapter")

    if mode == "Ref2VA":
        items = iter_reference_items(pack)
        if profile.send_ref_images:
            for item in items:
                if item["kind"] != "image":
                    continue
                _add_image_part(parts, f"{item['alias']} reference image follows", item["value"], profile.jpeg_quality)
        if profile.send_ref_videos:
            for item in items:
                if item["kind"] != "video":
                    continue
                if profile.direct_video and profile.api_format == "gemini_native":
                    continue
                parts.extend(_video_parts_for_item(item, user_prompt, profile))
        return parts

    if profile.send_keyframes:
        first = pack.get("first_frame")
        last = pack.get("last_frame")
        if mode in {"I2VA", "FL2VA"} and first is not None:
            _add_image_part(parts, "first_frame keyframe follows", first, profile.jpeg_quality)
        if mode in {"FL2VA", "L2VA"} and last is not None:
            _add_image_part(parts, "last_frame keyframe follows", last, profile.jpeg_quality)
    return parts
