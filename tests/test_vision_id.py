"""Unit tests for HA Whisker Pet ID Hybrid Fast-Path, MediaSource, and Gemini Vision."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _ensure_stubs() -> None:
    """Install minimal Home Assistant & aiohttp stubs for offline unit testing."""
    if "aiohttp" not in sys.modules:
        aiohttp = types.ModuleType("aiohttp")

        class ClientError(Exception):
            pass

        class ClientResponseError(ClientError):
            def __init__(self, status: int = 400, message: str = "Bad Request") -> None:
                super().__init__(message)
                self.status = status
                self.message = message

        aiohttp.ClientError = ClientError
        aiohttp.ClientResponseError = ClientResponseError
        sys.modules["aiohttp"] = aiohttp

    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    if "homeassistant.config_entries" not in sys.modules:
        ha_ce = types.ModuleType("homeassistant.config_entries")
        ha_ce.ConfigEntry = type("ConfigEntry", (), {})
        ha_ce.ConfigEntryState = SimpleNamespace(LOADED="loaded")
        sys.modules["homeassistant.config_entries"] = ha_ce
    if "homeassistant.core" not in sys.modules:
        ha_core = types.ModuleType("homeassistant.core")
        ha_core.HomeAssistant = type("HomeAssistant", (), {})
        sys.modules["homeassistant.core"] = ha_core
    if "homeassistant.exceptions" not in sys.modules:
        ha_exc = types.ModuleType("homeassistant.exceptions")
        ha_exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
        sys.modules["homeassistant.exceptions"] = ha_exc

    HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError

    if "homeassistant.components" not in sys.modules:
        sys.modules["homeassistant.components"] = types.ModuleType("homeassistant.components")

    if "homeassistant.components.media_player" not in sys.modules:
        mp = types.ModuleType("homeassistant.components.media_player")
        mp.MediaClass = SimpleNamespace(DIRECTORY="directory")
        mp.MediaType = SimpleNamespace(IMAGE="image")
        sys.modules["homeassistant.components.media_player"] = mp

    if "homeassistant.components.media_source" not in sys.modules:
        ms = types.ModuleType("homeassistant.components.media_source")
        ms_err = types.ModuleType("homeassistant.components.media_source.error")
        ms_models = types.ModuleType("homeassistant.components.media_source.models")

        class Unresolvable(HomeAssistantError):
            pass

        class MediaSource:
            def __init__(self, domain: str) -> None:
                self.domain = domain

        class PlayMedia:
            def __init__(self, *, url: str, mime_type: str, path: Path | None = None) -> None:
                self.url = url
                self.mime_type = mime_type
                self.path = path

        class BrowseMediaSource:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        class MediaSourceItem:
            def __init__(self, identifier: str = "") -> None:
                self.identifier = identifier

        ms_err.Unresolvable = Unresolvable
        ms_models.MediaSource = MediaSource
        ms_models.PlayMedia = PlayMedia
        ms_models.BrowseMediaSource = BrowseMediaSource
        ms_models.MediaSourceItem = MediaSourceItem
        sys.modules["homeassistant.components.media_source"] = ms
        sys.modules["homeassistant.components.media_source.error"] = ms_err
        sys.modules["homeassistant.components.media_source.models"] = ms_models

    repo_root = Path(__file__).resolve().parents[1]
    comp_parent = repo_root / "custom_components"
    if "custom_components" not in sys.modules:
        cc = types.ModuleType("custom_components")
        cc.__path__ = [str(comp_parent)]
        sys.modules["custom_components"] = cc
    if "custom_components.ha_whisker_pet_id" not in sys.modules:
        pkg = types.ModuleType("custom_components.ha_whisker_pet_id")
        pkg.__path__ = [str(comp_parent / "ha_whisker_pet_id")]
        sys.modules["custom_components.ha_whisker_pet_id"] = pkg


_ensure_stubs()
media_source = importlib.import_module("custom_components.ha_whisker_pet_id.media_source")
vision_id = importlib.import_module("custom_components.ha_whisker_pet_id.vision_id")
Unresolvable = sys.modules["homeassistant.components.media_source.error"].Unresolvable


class TestBaselinesFastPathAndMediaSource(unittest.TestCase):
    """Tests for clean baselines, Hybrid Fast-Path, safety gates, and MediaSource."""

    def setUp(self) -> None:
        self.baselines = {
            "Jane": 8.58,
            "Oreo": 8.74,
            "Ember": 9.58,
            "Sterling": 10.08,
            "Lexi": 11.60,
        }

    def test_clean_baselines_ignore_single_outlier(self) -> None:
        pets = [
            {
                "name": "Jane",
                "estimated_weight_lbs": 11.29,
                "recent_weight_history": [
                    {"weight_lbs": 0.0},
                    {"weight_lbs": 8.42},
                    {"weight_lbs": 8.54},
                    {"weight_lbs": 8.58},
                    {"weight_lbs": 11.29},
                ],
            },
            {
                "name": "Lexi",
                "estimated_weight_lbs": 11.60,
                "recent_weight_history": [
                    {"weight_lbs": 11.50},
                    {"weight_lbs": 11.61},
                    {"weight_lbs": 11.75},
                ],
            },
        ]
        # Jane's spread (11.29 - 8.42 = 2.87 > 2.0) keeps clean stored baseline 8.58
        clean = vision_id.compute_clean_baselines(pets, {"Jane": 8.58})
        self.assertEqual(clean["Jane"], 8.58)
        self.assertEqual(clean["Lexi"], 11.61)

    def test_hybrid_fast_path_fires_only_for_unambiguous_outliers(self) -> None:
        # 11.29 lb Lexi assigned to Jane -> 0-token fast-path fires cleanly
        v_lexi_jane = {
            "event_id": "e1",
            "weight_lbs": 11.29,
            "assigned_pets": ["Jane"],
            "is_reassigned": False,
            "flags": ["weight_mismatch"],
        }
        res = vision_id.evaluate_hybrid_fast_path(v_lexi_jane, self.baselines)
        self.assertIsNotNone(res)
        self.assertEqual(res["recommended_pet"], "Lexi")
        self.assertEqual(res["stage"], "hybrid_fast_path")

        # 11.51 lb Lexi assigned to Ember -> fast-path fires cleanly
        v_lexi_ember = {
            "event_id": "e2",
            "weight_lbs": 11.51,
            "assigned_pets": ["Ember"],
            "is_reassigned": False,
            "flags": ["weight_mismatch"],
        }
        res_e = vision_id.evaluate_hybrid_fast_path(v_lexi_ember, self.baselines)
        self.assertIsNotNone(res_e)
        self.assertEqual(res_e["recommended_pet"], "Lexi")

        # 10.08 lb assigned to Jane -> Sterling vs Ember overlap -> must NOT fast-path (send to Gemini)
        v_ambig = {
            "event_id": "e3",
            "weight_lbs": 10.08,
            "assigned_pets": ["Jane"],
            "is_reassigned": False,
            "flags": ["weight_mismatch"],
        }
        self.assertIsNone(vision_id.evaluate_hybrid_fast_path(v_ambig, self.baselines))

        # 1.0 lb scale glitch -> must NOT fast-path
        v_glitch = {
            "event_id": "e4",
            "weight_lbs": 1.0,
            "assigned_pets": ["Jane"],
            "is_reassigned": False,
            "flags": ["scale_anomaly", "weight_mismatch"],
        }
        self.assertIsNone(vision_id.evaluate_hybrid_fast_path(v_glitch, self.baselines))

    def test_safety_guardrails(self) -> None:
        visit = {"weight_lbs": 9.62, "assigned_pets": ["Jane"]}

        # Unusual weight for Oreo (0.88 lb delta passes 1.25 lb, medium below high threshold -> needs_review)
        low_conf = {
            "recommended_pet": "Oreo",
            "confidence": "medium",
            "confidence_score": 0.78,
            "visual_match": "partial",
            "stage": "gemini_thumbnail",
            "reasoning": "Dark room.",
        }
        gated = vision_id.evaluate_reassignment_safety(
            low_conf, visit, self.baselines, mode="auto_reassign", min_confidence="high"
        )
        self.assertEqual(gated["action"], "needs_review")

        # Target weight delta > 1.25 lb downgrades even high confidence to needs_review
        big_weight_gap = {
            "recommended_pet": "Jane",
            "confidence": "high",
            "confidence_score": 0.92,
            "visual_match": "clear",
            "stage": "gemini_thumbnail",
            "reasoning": "Wrong cat.",
        }
        visit_heavy = {"weight_lbs": 11.40, "assigned_pets": ["Ember"]}
        gated2 = vision_id.evaluate_reassignment_safety(
            big_weight_gap, visit_heavy, self.baselines, mode="auto_reassign", min_confidence="high"
        )
        self.assertEqual(gated2["action"], "needs_review")

        # Dry run never mutates
        valid_lexi = {
            "recommended_pet": "Lexi",
            "confidence": "high",
            "confidence_score": 0.96,
            "visual_match": "clear",
            "stage": "gemini_thumbnail",
            "reasoning": "Warm tabby.",
        }
        gated_dry = vision_id.evaluate_reassignment_safety(
            valid_lexi, visit_heavy, self.baselines, mode="dry_run", min_confidence="high"
        )
        self.assertEqual(gated_dry["action"], "dry_run_reassign")

    def test_media_source_path_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refs = root / "refs"
            refs.mkdir()
            good = refs / "ref_jane.jpg"
            good.write_bytes(b"\xff\xd8\xff\xe0test")

            resolved = media_source.resolve_media_path(root, "refs/ref_jane.jpg")
            self.assertEqual(resolved, good.resolve())
            self.assertEqual(media_source.guess_mime_type(resolved), "image/jpeg")

            with self.assertRaises(Unresolvable):
                media_source.resolve_media_path(root, "../../etc/passwd")
            with self.assertRaises(Unresolvable):
                media_source.resolve_media_path(root, "refs/missing.jpg")


class TestAsyncGeminiVisionFlow(unittest.IsolatedAsyncioTestCase):
    """Tests for Stage 1 thumbnail -> Stage 2 video escalation and cleanup."""

    async def test_stage1_then_stage2_video_escalation_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refs_dir = root / "refs"
            refs_dir.mkdir()
            sheet = refs_dir / "ref_roster_sheet.jpg"
            sheet.write_bytes(b"\xff\xd8\xff\xe0sheet")

            ref_attachments = [
                {
                    "media_content_id": media_source.build_media_source_uri("refs/ref_roster_sheet.jpg"),
                    "media_content_type": "image/jpeg",
                }
            ]

            class FakeResp:
                def __init__(self, payload: bytes) -> None:
                    self._payload = payload

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *_args):
                    return False

                def raise_for_status(self) -> None:
                    pass

                async def read(self) -> bytes:
                    return self._payload

            websession = SimpleNamespace(
                get=lambda url, **kw: FakeResp(
                    b"\xff\xd8\xffthumb" if "thumb" in url else b"\x00\x00\x00\x18ftypmp42"
                )
            )

            ai_calls = []

            async def fake_async_call(domain, service, data, blocking=True, return_response=True):
                ai_calls.append(data)
                if len(ai_calls) == 1:
                    return {
                        "data": {
                            "recommended_pet": "UNCERTAIN",
                            "confidence": "low",
                            "confidence_score": "0.35",
                            "visual_match": "unclear",
                            "needs_video": "true",
                            "reasoning": "Dark blurry silhouette.",
                        }
                    }
                return {
                    "data": {
                        "recommended_pet": "Oreo",
                        "confidence": "high",
                        "confidence_score": "0.94",
                        "visual_match": "clear",
                        "needs_video": "false",
                        "reasoning": "Black-and-white tuxedo clearly visible entering globe.",
                    }
                }

            async def fake_executor(fn, *args):
                return fn(*args)

            hass = SimpleNamespace(
                async_add_executor_job=fake_executor,
                services=SimpleNamespace(
                    has_service=lambda d, s: d == "ai_task" and s == "generate_data",
                    async_call=fake_async_call,
                ),
            )

            orig_get_clip_urls = vision_id.async_get_clip_urls
            vision_id.async_get_clip_urls = AsyncMock(
                return_value={
                    "chunks": [
                        {"id": "1", "download_url": "https://s3.example/c0.mp4"},
                        {"id": "2", "download_url": "https://s3.example/c1.mp4"},
                        {"id": "3", "download_url": "https://s3.example/c2.mp4"},
                    ]
                }
            )
            try:
                result = await vision_id.async_verify_visit_with_gemini(
                    hass,
                    websession,
                    {
                        "event_id": "evt-oreo-night",
                        "local_time": "2026-11-27T01:56:39-06:00",
                        "weight_lbs": 8.70,
                        "duration_seconds": 83,
                        "assigned_pets": ["Jane"],
                        "flags": [],
                        "matched_clips": [
                            {
                                "clip_id": "353085410",
                                "thumbnail_url": "https://cdn.example/thumb.jpg",
                                "pet_detections": [{"petName": "Jane"}],
                            }
                        ],
                    },
                    [{"name": "Oreo", "breeds": ["DSH"], "gender": "male"}],
                    {"Oreo": 8.74, "Jane": 8.58},
                    ref_attachments,
                    uses_roster_sheet=True,
                    ref_pet_order=["Oreo"],
                    media_root=root,
                    ai_task_entity="ai_task.google_ai_task",
                    video_escalation="thumbnail_then_video",
                )
            finally:
                vision_id.async_get_clip_urls = orig_get_clip_urls

            self.assertEqual(len(ai_calls), 2)
            self.assertEqual(result["recommended_pet"], "Oreo")
            self.assertEqual(result["stage"], "gemini_video")
            self.assertEqual(result["confidence"], "high")
            # Stage 2 attached reference sheet + 2 MP4 chunks
            self.assertEqual(len(ai_calls[1]["attachments"]), 3)
            self.assertEqual(ai_calls[1]["attachments"][1]["media_content_type"], "video/mp4")
            # Temporary visit files cleaned up cleanly
            visits_dir = root / "visits"
            leftover = list(visits_dir.iterdir()) if visits_dir.exists() else []
            self.assertEqual(leftover, [])


if __name__ == "__main__":
    unittest.main()
