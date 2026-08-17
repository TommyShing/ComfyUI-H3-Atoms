from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from comfy_api.latest import ComfyExtension, io

from .api_client import request_chat_completion, request_responses_completion
from .profiles import APIProfile, API_FORMATS, REASONING_EFFORTS, TOKEN_PARAMETERS
from .prompt_builder import build_system_prompt, build_user_content
from .rules import RuleBundle
from .settings import (
    MAX_DURATION_SECONDS,
    WORKFLOW_MODE_OPTIONS,
    build_generation_settings,
    normalize_mode,
)
from .validation import validate_reference_pack


RULES_ROOT = Path(__file__).resolve().parents[1] / "rules"
GENERATION_SETTINGS = io.Custom("H3_GENERATION_SETTINGS")
REFERENCE_PACK = io.Custom("H3_REFERENCE_PACK")
API_PROFILE = io.Custom("H3_API_PROFILE")


def _normalize_refs(mapping: dict[str, Any] | None, prefix: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, (_, value) in enumerate((mapping or {}).items(), start=1):
        if value is not None:
            result[f"{prefix}{index}"] = value
    return result


def _normalize_reference_pack(
    ref_images: dict[str, Any] | None,
    ref_videos: dict[str, Any] | None,
    ref_video_audios: dict[str, Any] | None,
    ref_audios: dict[str, Any] | None,
) -> dict[str, Any]:
    suffix_to_index: dict[str, int] = {}
    for index, (name, value) in enumerate((ref_videos or {}).items(), start=1):
        if value is not None:
            suffix_to_index[name.rsplit("_", 1)[-1]] = index

    videos = _normalize_refs(ref_videos, "ref_video_")
    video_audios: dict[str, Any] = {}
    for name, value in (ref_video_audios or {}).items():
        if value is None:
            continue
        suffix = name.rsplit("_", 1)[-1]
        index = suffix_to_index.get(suffix)
        if index is None:
            raise ValueError(f"Paired video audio {name!r} has no matching reference video")
        video_audios[f"ref_video_audio_{index}"] = value

    return {
        "ref_images": _normalize_refs(ref_images, "ref_image_"),
        "ref_videos": videos,
        "ref_video_audios": video_audios,
        "ref_audios": _normalize_refs(ref_audios, "ref_audio_"),
        "first_frame": None,
        "last_frame": None,
    }


def _empty_reference_pack() -> dict[str, Any]:
    return {
        "ref_images": {},
        "ref_videos": {},
        "ref_video_audios": {},
        "ref_audios": {},
        "first_frame": None,
        "last_frame": None,
    }


def _call_official_image_to_video(
    clip,
    vae,
    prompt: str,
    width: int,
    height: int,
    length: int,
    first_frame,
    last_frame,
):
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageToVideo

    return MiniMaxH3ImageToVideo.execute(
        clip, vae, prompt, width, height, length, first_frame, last_frame
    )


def _call_official_reference_to_video(
    clip,
    vae,
    audio_vae,
    prompt: str,
    width: int,
    height: int,
    length: int,
    ref_image_size: str,
    ref_images,
    ref_videos,
    ref_video_audios,
    ref_audios,
):
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo

    return MiniMaxH3ReferenceToVideo.execute(
        clip,
        vae,
        audio_vae,
        prompt,
        width,
        height,
        length,
        ref_image_size,
        ref_images,
        ref_videos,
        ref_video_audios,
        ref_audios,
    )


class H3PromptRulesLoader(io.ComfyNode):
    """Compose the bundled H3 execution contract, core rules, mode guide, and optional style."""

    @classmethod
    def define_schema(cls):
        bundle = RuleBundle(RULES_ROOT)
        return io.Schema(
            node_id="H3PromptRulesLoader",
            display_name="H3 Prompt Rules Loader",
            category="prompt/minimax/h3",
            description=(
                "Loads the bundled MiniMax H3 prompt-writing rules and composes them for a "
                "workflow mode and one optional style."
            ),
            search_aliases=["h3 rules", "h3 prompt rules", "minimax h3 rules"],
            inputs=[
                io.Combo.Input(
                    "rule_version",
                    options=["Bundled Official"],
                    default="Bundled Official",
                    tooltip="Which rule bundle to use. Only the version-controlled bundled rules are available in this release.",
                ),
                io.Combo.Input(
                    "workflow_mode",
                    options=list(WORKFLOW_MODE_OPTIONS),
                    default="T2VA",
                    tooltip="H3 workflow mode. FULL_REFERENCE is normalized to Ref2VA.",
                ),
                io.Combo.Input(
                    "style",
                    options=list(bundle.styles),
                    default="None",
                    tooltip="Optional prompt-only MiniMax style adaptation. None keeps only the core H3 rules.",
                ),
            ],
            outputs=[io.String.Output(display_name="rules")],
        )

    @classmethod
    def execute(cls, rule_version: str, workflow_mode: str, style: str) -> io.NodeOutput:
        if rule_version != "Bundled Official":
            raise ValueError(f"Unsupported rule_version: {rule_version!r}")
        rules = RuleBundle(RULES_ROOT).compose(workflow_mode, style)
        return io.NodeOutput(rules)


class H3GenerationSettingsPack(io.ComfyNode):
    """Build normalized H3 generation facts from mode, resolution, and requested duration."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3GenerationSettingsPack",
            display_name="H3 Generation Settings Pack",
            category="prompt/minimax/h3",
            description=(
                "Normalizes workflow mode and aligns duration to the H3 24 fps 17k+5 frame grid. "
                "The packed settings feed the LLM process and later H3 conditioning."
            ),
            search_aliases=["h3 settings", "h3 generation settings", "minimax h3 settings"],
            inputs=[
                io.Combo.Input(
                    "workflow_mode",
                    options=list(WORKFLOW_MODE_OPTIONS),
                    default="T2VA",
                    tooltip="H3 workflow mode. FULL_REFERENCE is normalized to Ref2VA.",
                ),
                io.Int.Input(
                    "width",
                    default=1344,
                    min=32,
                    max=16384,
                    step=32,
                    tooltip="Generation width.",
                ),
                io.Int.Input(
                    "height",
                    default=768,
                    min=32,
                    max=16384,
                    step=32,
                    tooltip="Generation height.",
                ),
                io.Float.Input(
                    "duration",
                    default=5.0,
                    min=0.1,
                    max=MAX_DURATION_SECONDS,
                    step=0.1,
                    round=3,
                    tooltip="Requested duration in seconds. Frame count snaps up to the H3 17k+5 grid.",
                ),
            ],
            outputs=[GENERATION_SETTINGS.Output(display_name="generation_settings")],
        )

    @classmethod
    def execute(cls, workflow_mode: str, width: int, height: int, duration: float) -> io.NodeOutput:
        settings = build_generation_settings(workflow_mode, width, height, duration)
        return io.NodeOutput(settings)


class H3ReferencePack(io.ComfyNode):
    """Package reference media and keyframes into the custom H3_REFERENCE_PACK type."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3ReferencePack",
            display_name="H3 Reference Pack",
            category="prompt/minimax/h3",
            description=(
                "Normalizes connected reference images, video-frame batches, paired video audio, "
                "standalone audio, and optional first/last keyframes into one media pack."
            ),
            search_aliases=["h3 media", "h3 reference", "minimax h3 media"],
            inputs=[
                io.Autogrow.Input(
                    "ref_images",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_image"),
                        prefix="ref_image_",
                        min=0,
                        max=9,
                    ),
                    tooltip="Reference images (max 9).",
                ),
                io.Autogrow.Input(
                    "ref_videos",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_video"),
                        prefix="ref_video_",
                        min=0,
                        max=3,
                    ),
                    tooltip="Reference video frame batches at 24 fps (max 3).",
                ),
                io.Autogrow.Input(
                    "ref_video_audios",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_video_audio"),
                        prefix="ref_video_audio_",
                        min=0,
                        max=3,
                    ),
                    tooltip="Soundtracks paired by number with the reference videos (max 3).",
                ),
                io.Autogrow.Input(
                    "ref_audios",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_audio"),
                        prefix="ref_audio_",
                        min=0,
                        max=3,
                    ),
                    tooltip="Standalone reference audio (max 3).",
                ),
                io.Image.Input("first_frame", optional=True),
                io.Image.Input("last_frame", optional=True),
            ],
            outputs=[REFERENCE_PACK.Output(display_name="reference_pack")],
        )

    @classmethod
    def execute(
        cls,
        ref_images=None,
        ref_videos=None,
        ref_video_audios=None,
        ref_audios=None,
        first_frame=None,
        last_frame=None,
    ) -> io.NodeOutput:
        pack = _normalize_reference_pack(ref_images, ref_videos, ref_video_audios, ref_audios)
        pack["first_frame"] = first_frame
        pack["last_frame"] = last_frame
        return io.NodeOutput(pack)


class H3APIProfile(io.ComfyNode):
    """Build a non-secret OpenAI-compatible API profile."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3APIProfile",
            display_name="H3 API Profile",
            category="prompt/minimax/h3",
            description=(
                "Defines an OpenAI-compatible completion profile. API keys are read from an "
                "environment variable at request time and are never stored in the workflow."
            ),
            search_aliases=["h3 api", "h3 profile", "minimax h3 api"],
            inputs=[
                io.String.Input("profile_name", default="default"),
                io.String.Input("base_url", default="https://api.example.com/v1"),
                io.String.Input("model", default="glm-4.5v"),
                io.String.Input("api_key_env", default="H3_API_KEY"),
                io.Combo.Input(
                    "api_format",
                    options=list(API_FORMATS),
                    default="completions",
                    tooltip="completions uses chat/completions; responses uses the Responses API; gemini_native is the planned Google-native adapter.",
                ),
                io.Combo.Input(
                    "token_parameter",
                    options=list(TOKEN_PARAMETERS),
                    default="max_completion_tokens",
                ),
                io.Int.Input("max_tokens", default=8192, min=1, max=131072),
                io.Combo.Input(
                    "reasoning_effort",
                    options=list(REASONING_EFFORTS),
                    default="disabled",
                ),
                io.Float.Input("timeout_seconds", default=120.0, min=1.0, max=600.0),
                io.Boolean.Input("send_ref_images", default=True),
                io.Boolean.Input("send_ref_videos", default=True),
                io.Boolean.Input("send_ref_audio", default=False),
                io.Boolean.Input("send_keyframes", default=True),
                io.Boolean.Input("direct_video", default=False),
                io.Int.Input("jpeg_quality", default=90, min=1, max=100),
                io.Int.Input("sampled_video_frames", default=3, min=1, max=12),
            ],
            outputs=[API_PROFILE.Output(display_name="api_profile")],
        )

    @classmethod
    def execute(
        cls,
        profile_name: str,
        base_url: str,
        model: str,
        api_key_env: str,
        api_format: str,
        token_parameter: str,
        max_tokens: int,
        reasoning_effort: str,
        timeout_seconds: float,
        send_ref_images: bool,
        send_ref_videos: bool,
        send_ref_audio: bool,
        send_keyframes: bool,
        direct_video: bool,
        jpeg_quality: int,
        sampled_video_frames: int,
    ) -> io.NodeOutput:
        profile = APIProfile(
            name=profile_name,
            base_url=base_url,
            model=model,
            api_key_env=api_key_env,
            api_format=api_format,
            token_parameter=token_parameter,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            send_ref_images=send_ref_images,
            send_ref_videos=send_ref_videos,
            send_ref_audio=send_ref_audio,
            send_keyframes=send_keyframes,
            direct_video=direct_video,
            jpeg_quality=jpeg_quality,
            sampled_video_frames=sampled_video_frames,
        )
        profile.validate()
        return io.NodeOutput(asdict(profile))


class H3LLMPromptProcess(io.ComfyNode):
    """Compile one multimodal OpenAI-compatible request and return the final H3 prompt."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3LLMPromptProcess",
            display_name="H3 LLM Prompt Process",
            category="prompt/minimax/h3",
            description=(
                "Sends rules, generation settings, user prompt, and selected reference media to an "
                "OpenAI-compatible API. Returns final_prompt and an output_msg diagnostic string."
            ),
            search_aliases=["h3 llm", "h3 prompt process", "minimax h3 llm"],
            inputs=[
                REFERENCE_PACK.Input("reference_pack", optional=True),
                GENERATION_SETTINGS.Input("generation_settings"),
                io.String.Input("rules", multiline=True),
                io.String.Input("user_prompt", multiline=True),
                API_PROFILE.Input("api_profile"),
            ],
            outputs=[
                io.String.Output(display_name="final_prompt"),
                io.String.Output(display_name="output_msg"),
            ],
        )

    @classmethod
    def execute(
        cls,
        reference_pack=None,
        generation_settings=None,
        rules=None,
        user_prompt=None,
        api_profile=None,
    ) -> io.NodeOutput:
        try:
            if not rules or not rules.strip():
                raise ValueError("rules must not be empty")
            if not isinstance(api_profile, dict):
                raise ValueError("api_profile must be connected to an H3 API Profile node")
            profile = APIProfile.from_mapping(api_profile)
            pack = reference_pack if isinstance(reference_pack, dict) else _empty_reference_pack()
            validate_reference_pack(generation_settings, pack)
            system_prompt = build_system_prompt(rules, generation_settings)
            user_content = build_user_content(user_prompt or "", pack, generation_settings, profile)
            api_key = os.getenv(profile.api_key_env, "").strip() if profile.api_key_env else ""
            if not api_key:
                raise ValueError(f"API key environment variable {profile.api_key_env!r} is not set")
            if profile.api_format == "responses":
                result = request_responses_completion(profile, api_key, system_prompt, user_content)
            elif profile.api_format == "gemini_native":
                raise ValueError("Gemini Native adapter is not implemented yet; use completions or responses")
            else:
                result = request_chat_completion(profile, api_key, system_prompt, user_content)
            if result.truncated:
                return io.NodeOutput(
                    "",
                    f"WARNING finish_reason={result.finish_reason!r}; output truncated and not returned",
                )
            message = f"OK model={profile.model} finish_reason={result.finish_reason!r}"
            if result.usage:
                message += f" usage={json.dumps(result.usage, ensure_ascii=False)}"
            return io.NodeOutput(result.content, message)
        except Exception as exc:
            return io.NodeOutput("", f"ERROR {type(exc).__name__}: {exc}")


class H3UnifiedEncode(io.ComfyNode):
    """Route an H3 prompt and media pack into the official ComfyUI H3 conditioning nodes."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3UnifiedEncode",
            display_name="H3 Unified Encode",
            category="model/conditioning/minimax",
            description=(
                "Delegates to MiniMaxH3ImageToVideo for T2VA/I2VA/FL2VA/L2VA and to "
                "MiniMaxH3ReferenceToVideo for Ref2VA."
            ),
            search_aliases=["h3 encode", "h3 unified", "minimax h3 encode"],
            inputs=[
                REFERENCE_PACK.Input("reference_pack", optional=True),
                GENERATION_SETTINGS.Input("generation_settings"),
                io.String.Input("prompt", multiline=True, dynamic_prompts=False),
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae", optional=True),
                io.Combo.Input(
                    "ref_image_size",
                    options=["match", "max"],
                    default="match",
                    tooltip="Reference image sizing used by the official Ref2VA node.",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
            ],
        )

    @classmethod
    def execute(
        cls,
        reference_pack=None,
        generation_settings=None,
        prompt=None,
        clip=None,
        vae=None,
        audio_vae=None,
        ref_image_size="match",
    ) -> io.NodeOutput:
        pack = reference_pack if isinstance(reference_pack, dict) else _empty_reference_pack()
        validate_reference_pack(generation_settings, pack)
        mode = normalize_mode(generation_settings["workflow_mode"])
        width = int(generation_settings["width"])
        height = int(generation_settings["height"])
        length = int(generation_settings["frame_count"])
        if mode == "Ref2VA":
            if audio_vae is None:
                raise ValueError("Ref2VA requires audio_vae")
            return _call_official_reference_to_video(
                clip=clip,
                vae=vae,
                audio_vae=audio_vae,
                prompt=prompt or "",
                width=width,
                height=height,
                length=length,
                ref_image_size=ref_image_size,
                ref_images=pack["ref_images"],
                ref_videos=pack["ref_videos"],
                ref_video_audios=pack["ref_video_audios"],
                ref_audios=pack["ref_audios"],
            )
        return _call_official_image_to_video(
            clip=clip,
            vae=vae,
            prompt=prompt or "",
            width=width,
            height=height,
            length=length,
            first_frame=pack["first_frame"],
            last_frame=pack["last_frame"],
        )


class H3PromptToolsExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            H3PromptRulesLoader,
            H3GenerationSettingsPack,
            H3ReferencePack,
            H3APIProfile,
            H3LLMPromptProcess,
            H3UnifiedEncode,
        ]


async def comfy_entrypoint() -> H3PromptToolsExtension:
    return H3PromptToolsExtension()
