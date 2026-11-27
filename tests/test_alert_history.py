"""Unit tests for persistent historical alert tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
import types
import unittest
from types import SimpleNamespace


def _ensure_stubs() -> None:
    """Ensure minimal Home Assistant stubs including helpers.storage exist."""
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
        ha_core.CALLBACK_TYPE = object
        ha_core.callback = lambda fn: fn
        sys.modules["homeassistant.core"] = ha_core
    else:
        ha_core = sys.modules["homeassistant.core"]
        if not hasattr(ha_core, "CALLBACK_TYPE"):
            ha_core.CALLBACK_TYPE = object
        if not hasattr(ha_core, "callback"):
            ha_core.callback = lambda fn: fn
    if "homeassistant.exceptions" not in sys.modules:
        ha_exc = types.ModuleType("homeassistant.exceptions")
        ha_exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
        sys.modules["homeassistant.exceptions"] = ha_exc

    if "homeassistant.helpers" not in sys.modules:
        sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")

    if "homeassistant.helpers.storage" not in sys.modules:
        ha_storage = types.ModuleType("homeassistant.helpers.storage")

        class Store:
            def __init__(self, hass, version: int, key: str) -> None:
                self.hass = hass
                self.version = version
                self.key = key
                self.data = None

            async def async_load(self):
                return self.data

            async def async_save(self, data):
                self.data = data

        ha_storage.Store = Store
        sys.modules["homeassistant.helpers.storage"] = ha_storage

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
alert_history = importlib.import_module("custom_components.ha_whisker_pet_id.alert_history")


class TestAlertHistoryManager(unittest.IsolatedAsyncioTestCase):
    """Tests for cluster/summary/review archiving, auto-resolve, and filtering."""

    def _make_hass(self):
        events = []
        bus = SimpleNamespace(
            async_fire=lambda event_type, data: events.append((event_type, data))
        )
        hass = SimpleNamespace(bus=bus)
        return hass, events

    async def test_cluster_and_summary_lifecycle_and_resolution(self) -> None:
        hass, events = self._make_hass()
        mgr = alert_history.AlertHistoryManager(hass, max_entries=20)
        listener_hits = 0

        def _on_change():
            nonlocal listener_hits
            listener_hits += 1

        unsub = mgr.add_listener(_on_change)
        t1 = datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)

        report_alert = {
            "overall_status": "alert",
            "headline": "Lexi clustering detected.",
            "clusters_detected": 1,
            "flagged_visits_count": 2,
            "generation_mode": "gemini",
            "alert_pets": ["Lexi"],
            "pet_summaries": {
                "Lexi": {"status": "alert", "summary": "3 visits in 15m"},
                "Jane": {"status": "normal", "summary": "Normal"},
            },
            "clusters": [
                {
                    "pet_name": "Lexi",
                    "start": "2026-11-27T12:40:00+00:00",
                    "end": "2026-11-27T12:55:00+00:00",
                    "count": 3,
                    "zero_waste_count": 1,
                    "duration_minutes": 15.0,
                }
            ],
        }
        res1 = await mgr.async_record_health_report(
            report_alert, notified_services=["notify.family"], now=t1
        )
        self.assertEqual(res1, {"opened": 2, "resolved": 0})
        self.assertEqual(listener_hits, 1)
        self.assertEqual(len([e for e in events if e[1]["action"] == "opened"]), 2)

        payload1 = mgr.get_sensor_payload()
        self.assertEqual(payload1["active_count"], 2)
        self.assertEqual(payload1["counts_by_pet"]["Lexi"], 2)

        # Deduplicate repeated identical report (no extra opened entries)
        res_dup = await mgr.async_record_health_report(
            report_alert, notified_services=["notify.family"], now=t1 + timedelta(minutes=5)
        )
        self.assertEqual(res_dup, {"opened": 0, "resolved": 0})
        self.assertEqual(mgr.get_sensor_payload()["total_logged"], 2)

        # Resolve both when clusters clear & overall_status becomes normal
        t2 = t1 + timedelta(hours=4)
        report_normal = {
            "overall_status": "normal",
            "headline": "All normal.",
            "clusters_detected": 0,
            "flagged_visits_count": 0,
            "generation_mode": "gemini",
            "alert_pets": [],
            "pet_summaries": {"Lexi": {"status": "normal", "summary": "Normal"}},
            "clusters": [],
        }
        res2 = await mgr.async_record_health_report(report_normal, now=t2)
        self.assertEqual(res2, {"opened": 0, "resolved": 2})
        self.assertEqual(mgr.get_sensor_payload()["active_count"], 0)
        self.assertEqual(mgr.get_sensor_payload()["resolved_count"], 2)
        unsub()

    async def test_pet_id_review_query_and_eviction(self) -> None:
        hass, _ = self._make_hass()
        mgr = alert_history.AlertHistoryManager(hass, max_entries=10)
        now = datetime(2026, 11, 27, 14, 0, tzinfo=timezone.utc)

        await mgr.async_record_pet_id_review(
            {
                "processed_at": (now - timedelta(hours=1)).isoformat(),
                "event_id": "evt-oreo-1",
                "weight_lbs": 9.62,
                "from_pet": "Jane",
                "to_pet": "Oreo",
                "stage": "gemini_thumbnail",
                "confidence": "high",
                "confidence_score": 0.92,
                "visual_match": "clear",
                "reasoning": "Target weight delta > 1.25 lb vs Jane; looks like Oreo.",
            },
            notified_services=["notify.family"],
            now=now,
        )

        # Query filters
        q_oreo = mgr.query(pet="Oreo", source="pet_id_review", active_only=True, now=now)
        self.assertEqual(q_oreo["returned_count"], 1)
        self.assertEqual(q_oreo["alerts"][0]["status"], "active")

        # Resolve review when reassigned
        resolved = await mgr.async_resolve_pet_id_review("evt-oreo-1", now=now)
        self.assertTrue(resolved)
        q_active = mgr.query(active_only=True, now=now)
        self.assertEqual(q_active["returned_count"], 0)

        # Bound eviction at max_entries=10
        for idx in range(15):
            await mgr.async_record_pet_id_review(
                {
                    "processed_at": (now + timedelta(minutes=idx)).isoformat(),
                    "event_id": f"evt-bulk-{idx}",
                    "weight_lbs": 9.8,
                    "from_pet": "Ember",
                    "to_pet": None,
                    "reasoning": f"Uncertain {idx}",
                },
                now=now + timedelta(minutes=idx),
            )
        self.assertEqual(mgr.query()["total_logged"], 10)


if __name__ == "__main__":
    unittest.main()
