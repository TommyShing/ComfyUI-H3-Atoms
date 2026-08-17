from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from h3_prompt_tools.api_client import CompletionResult


COMFY_ROOT = Path(r"E:\Stable Diffusion\ComfyUI-aki-v3.2\ComfyUI")
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))

NODE_IMPORT_ERROR = None
try:
    from h3_prompt_tools import nodes
except Exception as exc:  # pragma: no cover - exercised only when ComfyUI API is unavailable
    nodes = None
    NODE_IMPORT_ERROR = exc


def _api_profile_dict(**overrides):
    profile = {
        "name": "test",
        "base_url": "https://example.com/v1",
        "model": "glm",
        "api_key_env": "H3_API_KEY",
        "api_format": "completions",
        "token_parameter": "max_completion_tokens",
        "max_tokens": 8192,
        "reasoning_effort": "disabled",
        "timeout_seconds": 120.0,
        "send_ref_images": True,
        "send_ref_videos": True,
        "send_ref_audio": False,
        "send_keyframes": True,
        "direct_video": False,
        "jpeg_quality": 90,
        "sampled_video_frames": 3,
    }
    profile.update(overrides)
    return profile


def _settings(mode="T2VA"):
    return nodes.H3GenerationSettingsPack.execute(
        workflow_mode=mode,
        width=1344,
        height=768,
        duration=5.0,
    )[0]


@unittest.skipUnless(nodes is not None, f"ComfyUI comfy_api unavailable: {NODE_IMPORT_ERROR}")
class NodeSchemaTests(unittest.TestCase):
    def test_extension_registers_nodes(self):
        extension = asyncio.run(nodes.comfy_entrypoint())
        classes = asyncio.run(extension.get_node_list())
        names = {cls.GET_SCHEMA().node_id for cls in classes}
        self.assertEqual(
            names,
            {
                "H3PromptRulesLoader",
                "H3GenerationSettingsPack",
                "H3ReferencePack",
                "H3APIProfile",
                "H3LLMPromptProcess",
                "H3UnifiedEncode",
            },
        )

    def test_rules_loader_schema_and_execution(self):
        schema = nodes.H3PromptRulesLoader.GET_SCHEMA()
        self.assertEqual(schema.node_id, "H3PromptRulesLoader")
        self.assertEqual([output.io_type for output in schema.outputs], ["STRING"])

        result = nodes.H3PromptRulesLoader.execute(
            rule_version="Bundled Official",
            workflow_mode="FULL_REFERENCE",
            style="Handdrawn Live",
        )
        rules = result[0]
        self.assertIn("H3 Core Rules", rules)
        self.assertIn("Optional Style Contract", rules)
        self.assertIn("Handdrawn Live-Action Fusion", rules)

    def test_settings_pack_schema_and_execution(self):
        schema = nodes.H3GenerationSettingsPack.GET_SCHEMA()
        self.assertEqual(schema.node_id, "H3GenerationSettingsPack")
        self.assertEqual([output.io_type for output in schema.outputs], ["H3_GENERATION_SETTINGS"])

        result = nodes.H3GenerationSettingsPack.execute(
            workflow_mode="FULL_REFERENCE",
            width=1344,
            height=768,
            duration=5.0,
        )
        settings = result[0]
        self.assertEqual(settings["workflow_mode"], "Ref2VA")
        self.assertEqual(settings["frame_count"], 124)
        self.assertEqual(settings["frame_count"] % 17, 5)

    def test_reference_pack_normalizes_autogrow_inputs(self):
        first = object()
        last = object()
        image_a = object()
        image_b = object()
        video = object()
        soundtrack = object()
        audio = object()

        result = nodes.H3ReferencePack.execute(
            ref_images={"ref_image_0": image_a, "ref_image_2": image_b},
            ref_videos={"ref_video_0": video},
            ref_video_audios={"ref_video_audio_0": soundtrack},
            ref_audios={"ref_audio_0": audio},
            first_frame=first,
            last_frame=last,
        )
        pack = result[0]
        self.assertEqual(list(pack["ref_images"]), ["ref_image_1", "ref_image_2"])
        self.assertIs(pack["ref_images"]["ref_image_1"], image_a)
        self.assertEqual(list(pack["ref_videos"]), ["ref_video_1"])
        self.assertEqual(list(pack["ref_video_audios"]), ["ref_video_audio_1"])
        self.assertEqual(list(pack["ref_audios"]), ["ref_audio_1"])
        self.assertIs(pack["first_frame"], first)
        self.assertIs(pack["last_frame"], last)

    def test_reference_pack_rejects_unpaired_video_audio(self):
        with self.assertRaisesRegex(ValueError, "no matching reference video"):
            nodes.H3ReferencePack.execute(
                ref_images={},
                ref_videos={"ref_video_0": object()},
                ref_video_audios={"ref_video_audio_9": object()},
                ref_audios={},
            )

    def test_api_profile_schema_and_execution(self):
        schema = nodes.H3APIProfile.GET_SCHEMA()
        self.assertEqual(schema.node_id, "H3APIProfile")
        self.assertEqual([output.io_type for output in schema.outputs], ["H3_API_PROFILE"])

        result = nodes.H3APIProfile.execute(
            profile_name="local",
            base_url="https://example.com/v1",
            model="glm",
            api_key_env="H3_API_KEY",
            api_format="completions",
            token_parameter="max_completion_tokens",
            max_tokens=2048,
            reasoning_effort="disabled",
            timeout_seconds=30.0,
            send_ref_images=True,
            send_ref_videos=False,
            send_ref_audio=False,
            send_keyframes=True,
            direct_video=False,
            jpeg_quality=85,
            sampled_video_frames=2,
        )
        profile = result[0]
        self.assertEqual(profile["name"], "local")
        self.assertEqual(profile["model"], "glm")
        self.assertNotIn("api_key", profile)

    def test_llm_prompt_process_success(self):
        with mock.patch.dict(os.environ, {"H3_API_KEY": "secret"}, clear=False), mock.patch.object(
            nodes,
            "request_chat_completion",
            return_value=CompletionResult("final prompt", "stop", {"total_tokens": 10}, {}),
        ) as request_mock:
            result = nodes.H3LLMPromptProcess.execute(
                reference_pack=None,
                generation_settings=_settings("T2VA"),
                rules="Execution contract\nCore rules",
                user_prompt="A quiet scene.",
                api_profile=_api_profile_dict(),
            )
        self.assertEqual(result[0], "final prompt")
        self.assertIn("finish_reason='stop'", result[1])
        request_mock.assert_called_once()
        user_content = request_mock.call_args.args[3]
        self.assertTrue(any(part.get("type") == "text" for part in user_content))

    def test_llm_prompt_process_returns_error_string(self):
        result = nodes.H3LLMPromptProcess.execute(
            reference_pack=None,
            generation_settings=_settings("T2VA"),
            rules="rules",
            user_prompt="hello",
            api_profile=_api_profile_dict(api_key_env="MISSING_H3_KEY"),
        )
        self.assertEqual(result[0], "")
        self.assertTrue(result[1].startswith("ERROR "))

    def test_unified_encode_routes_image_mode(self):
        with mock.patch.object(
            nodes,
            "_call_official_image_to_video",
            return_value=nodes.io.NodeOutput("positive", "latent"),
        ) as official:
            result = nodes.H3UnifiedEncode.execute(
                reference_pack=None,
                generation_settings=_settings("T2VA"),
                prompt="prompt",
                clip=object(),
                vae=object(),
            )
        self.assertEqual(result[0], "positive")
        self.assertEqual(result[1], "latent")
        self.assertIsNone(official.call_args.kwargs["first_frame"])
        self.assertIsNone(official.call_args.kwargs["last_frame"])

    def test_unified_encode_routes_reference_mode(self):
        with mock.patch.object(
            nodes,
            "_call_official_reference_to_video",
            return_value=nodes.io.NodeOutput("positive", "latent"),
        ) as official:
            result = nodes.H3UnifiedEncode.execute(
                reference_pack=None,
                generation_settings=_settings("FULL_REFERENCE"),
                prompt="prompt",
                clip=object(),
                vae=object(),
                audio_vae=object(),
                ref_image_size="max",
            )
        self.assertEqual(result[0], "positive")
        self.assertEqual(result[1], "latent")
        self.assertEqual(official.call_args.kwargs["ref_image_size"], "max")
        self.assertIsNotNone(official.call_args.kwargs["audio_vae"])


if __name__ == "__main__":
    unittest.main()
