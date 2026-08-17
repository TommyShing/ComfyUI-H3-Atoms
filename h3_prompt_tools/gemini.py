from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from typing import Any


GEMINI_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"


def audio_to_wav_bytes(audio: dict[str, Any]) -> bytes:
    import numpy as np

    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    if getattr(waveform, "ndim", None) == 3:
        waveform = waveform[0]
    array = waveform.detach().cpu().numpy()
    if array.ndim == 2:
        channels = array.shape[0]
        pcm = (array.transpose(1, 0).reshape(-1) * 32767).astype("<i2")
    else:
        channels = 1
        pcm = (array * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(np.ascontiguousarray(pcm).tobytes())
    return buffer.getvalue()


def image_batch_to_mp4_bytes(images: Any, fps: float = 24.0, quality: int = 18) -> bytes:
    import av
    from PIL import Image

    if getattr(images, "ndim", None) == 4:
        frames = images
    elif isinstance(images, (list, tuple)):
        if len(images) == 0:
            raise ValueError("Reference video frame batch is empty")
        if getattr(images[0], "ndim", None) == 3:
            frames = images[0].unsqueeze(0)
        else:
            frames = images[0]
    else:
        raise ValueError("Reference video must be an IMAGE frame batch")
    if frames.shape[0] < 1:
        raise ValueError("Reference video frame batch is empty")
    height = int(frames.shape[1])
    width = int(frames.shape[2])
    numpy_frames = (
        frames.detach().cpu().clamp(0, 1).mul(255).round()
        .to(dtype=frames.dtype).numpy().astype("uint8")
    )
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="mp4") as container:
        stream = container.add_stream("h264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(quality), "preset": "veryfast"}
        for index in range(frames.shape[0]):
            image = Image.fromarray(numpy_frames[index][..., :3], mode="RGB")
            frame = av.VideoFrame.from_image(image)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buffer.getvalue()


def _urlopen(url: str, data: bytes | None, headers: dict[str, str], timeout: float):
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:4000]}") from exc


def _start_gemini_upload(api_key: str, filename: str, mime_type: str, content_length: int, timeout: float) -> str:
    url = f"{GEMINI_UPLOAD_URL}?key={urllib.parse.quote(api_key)}"
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(content_length),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    }
    body = json.dumps({"file": {"display_name": filename}}).encode("utf-8")
    with _urlopen(url, body, headers, timeout) as response:
        upload_url = response.headers.get("X-Goog-Upload-URL") or response.headers.get("x-goog-upload-url")
        if not upload_url:
            raise ValueError("Gemini Files API did not return X-Goog-Upload-URL")
        return upload_url


def _upload_gemini_bytes(upload_url: str, data: bytes, mime_type: str, timeout: float) -> dict[str, Any]:
    headers = {
        "Content-Length": str(len(data)),
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
        "Content-Type": mime_type,
    }
    with _urlopen(upload_url, data, headers, timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gemini Files API returned a non-object upload response")
    return payload


def _get_gemini_file(api_key: str, file_name: str, timeout: float) -> dict[str, Any]:
    url = f"{GEMINI_API_URL}/{file_name}?key={urllib.parse.quote(api_key)}"
    with _urlopen(url, None, {}, timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gemini Files API returned a non-object file response")
    return payload


def upload_file_to_gemini(
    api_key: str,
    filename: str,
    mime_type: str,
    data: bytes,
    timeout: float = 120.0,
    poll_interval: float = 1.0,
) -> str:
    upload_url = _start_gemini_upload(api_key, filename, mime_type, len(data), timeout)
    payload = _upload_gemini_bytes(upload_url, data, mime_type, timeout)
    file_info = payload.get("file")
    if not isinstance(file_info, dict):
        raise ValueError("Gemini Files API upload response has no file object")
    file_name = file_info.get("name")
    if not file_name:
        raise ValueError("Gemini Files API upload response has no file.name")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = _get_gemini_file(api_key, file_name, timeout)
        state = current.get("state")
        if state == "ACTIVE":
            file_uri = current.get("uri")
            if not file_uri:
                raise ValueError("Gemini Files API file has no uri")
            return file_uri
        if state == "FAILED":
            raise ValueError(f"Gemini Files API processing failed for {file_name}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Gemini Files API file {file_name} did not become ACTIVE within {timeout:.0f}s")


def upload_audio_to_gemini(api_key: str, audio: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    data = audio_to_wav_bytes(audio)
    file_uri = upload_file_to_gemini(api_key, "h3-audio.wav", "audio/wav", data, timeout=timeout)
    return {"fileData": {"mimeType": "audio/wav", "fileUri": file_uri}}


def upload_video_to_gemini(api_key: str, images: Any, timeout: float = 120.0, fps: float = 24.0) -> dict[str, Any]:
    data = image_batch_to_mp4_bytes(images, fps=fps)
    file_uri = upload_file_to_gemini(api_key, "h3-video.mp4", "video/mp4", data, timeout=timeout)
    return {"fileData": {"mimeType": "video/mp4", "fileUri": file_uri}}
