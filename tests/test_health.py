"""Unit tests for HA Whisker Pet ID health aggregation, clusters, and Gemini AI Task."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _ensure_ha_stubs() -> None:
    """Ensure minimal homeassistant/aiohttp stubs exist when running outside HA."""
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
        ha = types.ModuleType("homeassistant")
        ha_ce = types.ModuleType("homeassistant.config_entries")
        ha_core = types.ModuleType("homeassistant.core")
        ha_exc = types.ModuleType("homeassistant.exceptions")

        class ConfigEntry:
            pass

        class ConfigEntryState:
            LOADED = "loaded"

        class HomeAssistant:
            pass

        class HomeAssistantError(Exception):
            pass

        ha_ce.ConfigEntry = ConfigEntry
        ha_ce.ConfigEntryState = ConfigEntryState
        ha_core.HomeAssistant = HomeAssistant
        ha_exc.HomeAssistantError = HomeAssistantError

        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.config_entries"] = ha_ce
        sys.modules["homeassistant.core"] = ha_core
        sys.modules["homeassistant.exceptions"] = ha_exc

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


_ensure_ha_stubs()
health = importlib.import_module("custom_components.ha_whisker_pet_id.health")
HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError


class TestHealthAggregationAndClusters(unittest.TestCase):
    """Tests for telemetry context building, cluster detection, and fallback."""

    def test_detect_cluster_and_weight_mismatch_redirection(self) -> None:
        now = datetime(2026, 11, 27, 12, 30, tzinfo=timezone.utc)
        pets = [
            {"pet_id": "PET-LEXI", "name": "Lexi", "estimated_weight_lbs": 11.6},
            {"pet_id": "PET-JANE", "name": "Jane", "estimated_weight_lbs": 8.6},
        ]
        visits = [
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(minutes=25)).isoformat(),
                "local_time": (now - timedelta(minutes=25)).isoformat(),
                "assigned_pets": ["Lexi"],
                "weight_lbs": 11.62,
                "duration_seconds": 45,
                "waste_type": "Urine",
                "waste_weight": 0.0,
                "flags": [],
                "closest_pets_by_weight": [{"name": "Lexi"}],
            },
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(minutes=18)).isoformat(),
                "local_time": (now - timedelta(minutes=18)).isoformat(),
                "assigned_pets": ["Lexi"],
                "weight_lbs": 11.58,
                "duration_seconds": 62,
                "waste_type": "Urine",
                "waste_weight": 0.0,
                "flags": [],
                "closest_pets_by_weight": [{"name": "Lexi"}],
            },
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(minutes=10)).isoformat(),
                "local_time": (now - timedelta(minutes=10)).isoformat(),
                "assigned_pets": ["Lexi"],
                "weight_lbs": 11.60,
                "duration_seconds": 38,
                "waste_type": "Urine",
                "waste_weight": 12.0,
                "flags": [],
                "closest_pets_by_weight": [{"name": "Lexi"}],
            },
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(minutes=5)).isoformat(),
                "local_time": (now - timedelta(minutes=5)).isoformat(),
                "assigned_pets": ["Jane"],
                "weight_lbs": 11.55,
                "duration_seconds": 40,
                "waste_type": "Urine",
                "waste_weight": 0.0,
                "flags": ["weight_mismatch"],
                "closest_pets_by_weight": [{"name": "Lexi"}],
            },
        ]

        ctx = health.build_health_context(
            visits,
            pets,
            tz_name="America/Chicago",
            now=now,
            window_hours=48,
            cluster_window_minutes=20,
            cluster_min_visits=3,
        )
        self.assertEqual(ctx["total_visits"], 4)
        self.assertEqual(ctx["clusters_detected"], 1)
        self.assertTrue(ctx["pets"]["Lexi"]["cluster_detected"])
        self.assertEqual(ctx["pets"]["Lexi"]["cluster_max_count"], 3)
        self.assertEqual(ctx["pets"]["Lexi"]["suspected_redirected_visits"], 1)
        self.assertEqual(ctx["pets"]["Jane"]["weight_mismatch_count"], 1)

        fb = health.build_fallback_health_summary(ctx)
        self.assertEqual(fb["overall_status"], "alert")
        self.assertIn("Lexi", fb["alert_pets"])
        self.assertEqual(fb["generation_mode"], "fallback")

    def test_parse_notify_targets(self) -> None:
        targets = health.parse_notify_targets(
            "notify.mobile_app_brads_iphone_17, mobile_app_brads_ipad_air"
        )
        self.assertEqual(
            targets,
            [
                ("notify", "mobile_app_brads_iphone_17"),
                ("notify", "mobile_app_brads_ipad_air"),
            ],
        )


class TestAsyncGeminiAndNotify(unittest.IsolatedAsyncioTestCase):
    """Tests for ai_task integration, 429 fallback, and notifications."""

    async def test_gemini_ai_task_success_and_fallback_on_429(self) -> None:
        now = datetime(2026, 11, 27, 12, 30, tzinfo=timezone.utc)
        ctx = health.build_health_context(
            [],
            [{"pet_id": "PET-1", "name": "Lexi", "estimated_weight_lbs": 11.6}],
            now=now,
        )

        async_call_ok = AsyncMock(
            return_value={
                "data": {
                    "overall_status": "watch",
                    "headline": "Lexi had 0 visits in 48h window.",
                    "summary_markdown": "Summary text.",
                    "alert_pets": "Lexi",
                    "alert_message": "Watch Lexi.",
                    "pet_summaries_json": '{"Lexi": {"status": "watch", "summary": "No visits seen."}}',
                }
            }
        )
        hass_ok = SimpleNamespace(
            services=SimpleNamespace(
                has_service=lambda dom, svc: dom == "ai_task" and svc == "generate_data",
                async_call=async_call_ok,
            )
        )

        res_ok = await health.async_generate_ai_health_summary(
            hass_ok, ctx, ai_task_entity="ai_task.google_ai_task", use_ai=True
        )
        self.assertEqual(res_ok["generation_mode"], "gemini")
        self.assertEqual(res_ok["overall_status"], "watch")
        self.assertEqual(res_ok["alert_pets"], ["Lexi"])
        self.assertEqual(res_ok["pet_summaries"]["Lexi"]["status"], "watch")

        # 429 RESOURCE_EXHAUSTED error triggers deterministic fallback cleanly
        async_call_err = AsyncMock(
            side_effect=HomeAssistantError("429 RESOURCE_EXHAUSTED")
        )
        hass_err = SimpleNamespace(
            services=SimpleNamespace(
                has_service=lambda dom, svc: dom == "ai_task" and svc == "generate_data",
                async_call=async_call_err,
            )
        )
        res_fb = await health.async_generate_ai_health_summary(
            hass_err, ctx, ai_task_entity="ai_task.google_ai_task", use_ai=True
        )
        self.assertEqual(res_fb["generation_mode"], "fallback")
        self.assertIn("429 RESOURCE_EXHAUSTED", res_fb["ai_error"])

    async def test_send_health_notifications(self) -> None:
        calls = []

        async def fake_call(domain, service, data, blocking=True):
            calls.append((domain, service, data))

        hass = SimpleNamespace(
            services=SimpleNamespace(
                has_service=lambda dom, svc: dom == "notify" and svc == "mobile_app_brads_iphone_17",
                async_call=fake_call,
            )
        )
        sent = await health.async_send_health_notifications(
            hass,
            notify_target="notify.mobile_app_brads_iphone_17, notify.missing",
            title="Whisker Health Alert",
            message="Lexi clustered 3 visits in 15m.",
        )
        self.assertEqual(sent, ["notify.mobile_app_brads_iphone_17"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "mobile_app_brads_iphone_17")


class TestCleanBaselinesAndScaleAnomalyFiltering(unittest.TestCase):
    """Verify baseline_overrides and scale_anomaly redirect exclusion."""

    def test_baseline_overrides_and_ignores_scale_anomaly_redirects(self) -> None:
        now = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
        pets = [
            {"pet_id": "p-jane", "name": "Jane", "estimated_weight_lbs": 11.46},
            {"pet_id": "p-ember", "name": "Ember", "estimated_weight_lbs": 9.54},
        ]
        visits = [
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "assigned_pets": ["Jane"],
                "weight_lbs": 8.54,
                "duration_seconds": 60,
                "waste_type": "urine",
                "waste_weight": 50.0,
                "flags": [],
                "closest_pets_by_weight": [{"name": "Jane", "abs_delta_lbs": 0.0}],
            },
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "assigned_pets": [],
                "weight_lbs": 1.0,
                "duration_seconds": 15,
                "waste_type": None,
                "waste_weight": 0.0,
                "flags": ["unassigned", "scale_anomaly"],
                "closest_pets_by_weight": [{"name": "Ember", "abs_delta_lbs": 8.54}],
            },
        ]
        ctx = health.build_health_context(
            visits,
            pets,
            tz_name="UTC",
            now=now,
            baseline_overrides={"Jane": 8.54, "Ember": 9.58},
        )
        self.assertEqual(ctx["pets"]["Jane"]["baseline_weight_lbs"], 8.54)
        self.assertEqual(ctx["pets"]["Ember"]["baseline_weight_lbs"], 9.58)
        self.assertEqual(ctx["pets"]["Ember"]["suspected_redirected_visits"], 0)
        self.assertEqual(ctx["pets"]["Jane"]["weight_mismatch_count"], 0)

    def test_reassigned_visits_suppress_weight_mismatch_while_keeping_unreviewed_flags(
        self,
    ) -> None:
        now = datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc)
        pets = [
            {"pet_id": "p-ember", "name": "Ember", "estimated_weight_lbs": 9.58},
            {"pet_id": "p-sterling", "name": "Sterling", "estimated_weight_lbs": 9.91},
        ]
        visits = [
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "assigned_pets": ["Ember"],
                "is_reassigned": True,
                "weight_lbs": 10.23,
                "duration_seconds": 80,
                "waste_type": "urine",
                "waste_weight": 60.0,
                "flags": ["weight_mismatch"],
                "closest_pets_by_weight": [{"name": "Sterling", "abs_delta_lbs": 0.32}],
            },
            {
                "type": "PET_VISIT",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "assigned_pets": ["Sterling"],
                "is_reassigned": False,
                "weight_lbs": 8.20,
                "duration_seconds": 75,
                "waste_type": "urine",
                "waste_weight": 55.0,
                "flags": ["weight_mismatch"],
                "closest_pets_by_weight": [{"name": "Ember", "abs_delta_lbs": 1.38}],
            },
        ]
        ctx = health.build_health_context(
            visits,
            pets,
            tz_name="UTC",
            now=now,
            baseline_overrides={"Ember": 9.58, "Sterling": 9.91},
        )
        # Reassigned visit keeps health metrics but suppresses stale Pet ID alerts
        self.assertEqual(ctx["pets"]["Ember"]["visits_window"], 1)
        self.assertEqual(ctx["pets"]["Ember"]["avg_weight_lbs"], 10.23)
        self.assertEqual(ctx["pets"]["Ember"]["weight_mismatch_count"], 0)
        self.assertEqual(ctx["pets"]["Sterling"]["suspected_redirected_visits"], 0)
        self.assertEqual(ctx["recent_visits_sample"][0]["flags"], [])

        # Un-reassigned visit keeps full weight_mismatch detection and flags
        self.assertEqual(ctx["pets"]["Sterling"]["weight_mismatch_count"], 1)
        self.assertEqual(ctx["pets"]["Ember"]["suspected_redirected_visits"], 1)
        self.assertEqual(ctx["flagged_visits_count"], 1)
        self.assertEqual(ctx["recent_visits_sample"][1]["flags"], ["weight_mismatch"])


if __name__ == "__main__":
    unittest.main()
