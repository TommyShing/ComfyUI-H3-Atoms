from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from h3_prompt_tools.api_client import (
    build_payload,
    build_responses_payload,
    chat_completions_url,
    parse_response,
    parse_responses_response,
    request_chat_completion,
    request_responses_completion,
    responses_url,
)
from h3_prompt_tools.media import parse_video_timestamps
from h3_prompt_tools.profiles import APIProfile, ProfileStore
from h3_prompt_tools.prompt_builder import build_system_prompt, build_user_content, build_user_text
from h3_prompt_tools.rules import RuleBundle
from h3_prompt_tools.settings import build_generation_settings
from h3_prompt_tools.validation import validate_reference_pack


ROOT = Path(__file__).resolve().parents[1]


class RuleTests(unittest.TestCase):
    def test_core_only_and_style_composition(self):
        bundle = RuleBundle(ROOT / "rules")
        core = bundle.compose("I2VA", "None")
        styled = bundle.compose("I2VA", "Handdrawn Live")
        self.assertIn("H3 Core Rules", core)
        self.assertNotIn("Optional Style Contract", core)
        self.assertIn("Optional Style Contract", styled)
        self.assertIn("Handdrawn Live-Action Fusion", styled)


class SettingsTests(unittest.TestCase):
    def test_duration_aligns_to_h3_grid(self):
        settings = build_generation_settings("FULL_REFERENCE", 1344, 768, 5.0)
        self.assertEqual(settings["workflow_mode"], "Ref2VA")
        self.assertEqual(settings["frame_count"], 124)
        self.assertEqual(settings["frame_count"] % 17, 5)

    def test_duration_over_official_length_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, "official H3 requested-length"):
            build_generation_settings("T2VA", 1344, 768, 151.0)


class PromptBuilderTests(unittest.TestCase):
    def setUp(self):
        self.settings = build_generation_settings("FULL_REFERENCE", 1344, 768, 5.0)
        self.pack = {
            "ref_images": {"ref_image_1": object()},
            "ref_videos": {"ref_video_1": object()},
            "ref_video_audios": {"ref_video_audio_1": object()},
            "ref_audios": {"ref_audio_1": object()},
            "first_frame": None,
            "last_frame": None,
        }

    def test_system_prompt_includes_machine_facts(self):
        system = build_system_prompt("Core rules", self.settings)
        self.assertIn("Workflow mode: Ref2VA", system)
        self.assertIn("Frame count: 124", system)

    def test_user_text_lists_stable_aliases(self):
        text = build_user_text("Use <Video 1> and <Audio 1>.", self.pack, self.settings)
        self.assertIn("<Picture 1>", text)
        self.assertIn("<Video 1>", text)
        self.assertIn("<Audio 1>", text)
        self.assertIn("<Audio 2>", text)

    def test_user_content_rejects_unsupported_audio_send(self):
        profile = APIProfile(
            name="test",
            base_url="https://example.com/v1",
            model="glm",
            send_ref_audio=True,
        )
        with self.assertRaisesRegex(ValueError, "send_ref_audio"):
            build_user_content("hello", self.pack, self.settings, profile)


class ProfileTests(unittest.TestCase):
    def test_profile_does_not_persist_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            store = ProfileStore(path)
            profile = APIProfile(name="test", base_url="https://example.com/v1", model="model")
            store.save(profile, api_key="secret")
            self.assertEqual(store.resolve_api_key(profile), "secret")
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))
            self.assertTrue(store.public_list()[0]["has_api_key"])


class APIClientTests(unittest.TestCase):
    def setUp(self):
        self.profile = APIProfile(name="test", base_url="https://example.com/v1", model="glm")

    def test_url_and_optional_reasoning(self):
        self.assertEqual(chat_completions_url(self.profile.base_url), "https://example.com/v1/chat/completions")
        payload = build_payload(self.profile, "sys", "user")
        self.assertIn("max_completion_tokens", payload)
        self.assertNotIn("reasoning_effort", payload)

    def test_parse_finish_reason(self):
        parsed = parse_response({"choices": [{"message": {"content": "ok"}, "finish_reason": "length"}]})
        self.assertTrue(parsed.truncated)

    def test_responses_url_payload_and_parse(self):
        self.assertEqual(responses_url(self.profile.base_url), "https://example.com/v1/responses")
        payload = build_responses_payload(self.profile, "sys", [{"type": "text", "text": "hello"}])
        self.assertEqual(payload["max_output_tokens"], 8192)
        self.assertEqual(payload["input"][0]["content"][0]["type"], "input_text")
        parsed = parse_responses_response({"status": "incomplete", "output_text": "half", "usage": {"x": 1}})
        self.assertTrue(parsed.truncated)

    def test_responses_transport_injection(self):
        def transport(url, headers, body, timeout):
            self.assertEqual(url, "https://example.com/v1/responses")
            request = json.loads(body)
            self.assertEqual(request["model"], "glm")
            return 200, json.dumps({"status": "completed", "output_text": "final"}).encode()

        result = request_responses_completion(self.profile, "key", "sys", "user", transport=transport)
        self.assertEqual(result.content, "final")

    def test_transport_injection(self):
        def transport(url, headers, body, timeout):
            request = json.loads(body)
            self.assertEqual(request["model"], "glm")
            return 200, json.dumps({"choices": [{"message": {"content": "final"}, "finish_reason": "stop"}]}).encode()

        result = request_chat_completion(self.profile, "key", "sys", "user", transport=transport)
        self.assertEqual(result.content, "final")


class MediaAndValidationTests(unittest.TestCase):
    def test_timestamp_aliases(self):
        parsed = parse_video_timestamps("Use <Video 1>[t=2.4s] and @ref_video_1[t=5s]")
        self.assertEqual(parsed, {1: [2.4], 2: [5.0]})

    def test_mode_validation(self):
        settings = build_generation_settings("I2VA", 1344, 768, 5)
        pack = {"ref_images": {}, "ref_videos": {}, "ref_video_audios": {}, "ref_audios": {}, "first_frame": object(), "last_frame": None}
        validate_reference_pack(settings, pack)
        pack["last_frame"] = object()
        with self.assertRaisesRegex(ValueError, "only first_frame"):
            validate_reference_pack(settings, pack)


if __name__ == "__main__":
    unittest.main()
