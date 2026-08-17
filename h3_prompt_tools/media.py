from __future__ import annotations

import base64
import io
import re
from typing import Any


TIME_REFERENCE_RE = re.compile(
    r"(?:<Video\s+(?P<label_index>\d+)>|@ref_video_(?P<slot_index>\d+))\s*\[t=(?P<seconds>\d+(?:\.\d+)?)s\]",
    re.IGNORECASE,
)


def tensor_to_jpeg_data_url(image: Any, quality: int = 90) -> str:
    from PIL import Image

    tensor = image
    if getattr(tensor, "ndim", None) == 4:
        tensor = tensor[0]
    if getattr(tensor, "ndim", None) != 3:
        raise ValueError("IMAGE must be an HWC image or BHWC image batch")
    if tensor.shape[-1] < 3:
        raise ValueError("IMAGE must have at least three channels")
    array = tensor[..., :3].detach().cpu().clamp(0, 1).mul(255).round().to(dtype=getattr(__import__("torch"), "uint8")).numpy()
    pil = Image.fromarray(array, mode="RGB")
    buffer = io.BytesIO()
    pil.save(buffer, format="JPEG", quality=int(quality), optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def parse_video_timestamps(prompt: str) -> dict[int, list[float]]:
    result: dict[int, list[float]] = {}
    for match in TIME_REFERENCE_RE.finditer(prompt or ""):
        if match.group("label_index"):
            index = int(match.group("label_index"))
        else:
            index = int(match.group("slot_index")) + 1
        seconds = float(match.group("seconds"))
        result.setdefault(index, [])
        if seconds not in result[index]:
            result[index].append(seconds)
    return result


def sample_video_frames(video: Any, count: int = 3, timestamps: list[float] | None = None, fps: float = 24.0) -> list[tuple[Any, float]]:
    total = int(video.shape[0])
    if total < 1:
        raise ValueError("Reference video frame batch is empty")
    if timestamps:
        indices = []
        for seconds in timestamps:
            index = round(seconds * fps)
            if index < 0 or index >= total:
                raise ValueError(f"Video timestamp {seconds:.3f}s is outside a {total / fps:.3f}s frame batch")
            indices.append(index)
    elif count <= 1 or total == 1:
        indices = [0]
    else:
        indices = [round(i * (total - 1) / (count - 1)) for i in range(min(count, total))]
    unique = list(dict.fromkeys(indices))
    return [(video[index : index + 1], index / fps) for index in unique]

