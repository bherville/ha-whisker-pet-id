"""Unit tests for HA Whisker Pet ID API helpers."""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _install_ha_stubs() -> None:
    """Install minimal homeassistant/aiohttp stubs when running outside HA."""
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


_install_ha_stubs()
api = importlib.import_module("custom_components.ha_whisker_pet_id.api")
HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
ClientResponseError = sys.modules["aiohttp"].ClientResponseError
ConfigEntryState = sys.modules["homeassistant.config_entries"].ConfigEntryState


def _make_pet(pet_id: str, name: str, est_weight: float) -> SimpleNamespace:
    return SimpleNamespace(
        id=pet_id,
        name=name,
        estimated_weight=est_weight,
        last_weight_reading=est_weight,
        weight=est_weight,
        breeds=["Domestic_shorthair"],
        gender="FEMALE",
        pet_tag_id=None,
        weight_id_feature_enabled=True,
        image_url=None,
        is_active=True,
        weight_history=[],
        to_dict=lambda: {},
    )


class TestApiHelpers(unittest.TestCase):
    """Tests for synchronous normalization and analysis helpers."""

    def test_normalize_weight_lbs(self) -> None:
        self.assertEqual(api.normalize_weight_lbs(937.0), 9.37)
        self.assertEqual(api.normalize_weight_lbs(1153), 11.53)
        self.assertEqual(api.normalize_weight_lbs(8.55), 8.55)
        self.assertIsNone(api.normalize_weight_lbs(0))
        self.assertIsNone(api.normalize_weight_lbs(None))
        self.assertIsNone(api.normalize_weight_lbs(True))

    def test_resolve_pet_id(self) -> None:
        pets = [_make_pet("PET-JANE", "Jane", 8.37), _make_pet("PET-STERLING", "Sterling", 9.32)]
        account = SimpleNamespace(pets=pets)
        self.assertEqual(api.resolve_pet_id(account, "jane"), "PET-JANE")
        self.assertEqual(api.resolve_pet_id(account, "PET-STERLING"), "PET-STERLING")
        with self.assertRaises(HomeAssistantError):
            api.resolve_pet_id(account, "UnknownCat")

    def test_analyze_visit_flags_and_clip_matching(self) -> None:
        jane = _make_pet("PET-JANE", "Jane", 8.37)
        sterling = _make_pet("PET-STERLING", "Sterling", 9.32)
        pets_by_id = {"PET-JANE": jane, "PET-STERLING": sterling}
        all_pets = [jane, sterling]

        clips = [
            {
                "id": 99901,
                "eventType": "PET_VISIT",
                "createdAt": "2026-11-24T14:30:20Z",
                "hlsDuration": "00:25",
                "videoThumbnail": "https://example.com/thumb.jpg",
                "petDetections": ["PET-JANE"],
            }
        ]

        # Mismatched visit: 9.32 lb credited to Jane (8.37 lb baseline)
        act_mismatch = {
            "eventId": "evt-1",
            "messageId": "msg-1",
            "type": "PET_VISIT",
            "timestamp": "2026-11-24T14:30:00Z",
            "petWeight": 932.0,
            "wasteType": "Urine",
            "duration": 30,
            "petIds": ["PET-JANE"],
            "cameraEventIds": [],
        }
        res = api.analyze_visit(
            act_mismatch, pets_by_id, all_pets, clips, "America/Chicago"
        )
        self.assertEqual(res["weight_lbs"], 9.32)
        self.assertIn("weight_mismatch", res["flags"])
        self.assertNotIn("scale_anomaly", res["flags"])
        self.assertEqual(res["closest_pets_by_weight"][0]["name"], "Sterling")
        self.assertEqual(len(res["matched_clips"]), 1)
        self.assertEqual(res["matched_clips"][0]["clip_id"], "99901")
        self.assertEqual(res["matched_clips"][0]["matched_by"], "timestamp")

        # Scale anomaly + unassigned visit (11.53 lb)
        act_anomaly = {
            "eventId": "evt-2",
            "type": "PET_VISIT",
            "timestamp": "2026-11-24T14:35:00Z",
            "petWeight": 1153.0,
            "petIds": [],
            "cameraEventIds": ["99901"],
        }
        res_anom = api.analyze_visit(
            act_anomaly, pets_by_id, all_pets, clips, "America/Chicago"
        )
        self.assertEqual(res_anom["flags"], ["unassigned", "scale_anomaly"])
        self.assertEqual(res_anom["matched_clips"][0]["matched_by"], "id")


class TestAsyncApi(unittest.IsolatedAsyncioTestCase):
    """Tests for async Whisker API calls."""

    def _make_hass(self, account: SimpleNamespace, lr_coordinator: SimpleNamespace) -> SimpleNamespace:
        entry = SimpleNamespace(
            state=ConfigEntryState.LOADED,
            runtime_data=lr_coordinator,
        )
        return SimpleNamespace(
            config=SimpleNamespace(time_zone="America/Chicago"),
            config_entries=SimpleNamespace(async_entries=lambda domain: [entry]),
        )

    async def test_reassign_modes_and_error(self) -> None:
        jane = _make_pet("PET-JANE", "Jane", 8.37)
        sterling = _make_pet("PET-STERLING", "Sterling", 9.32)
        robot = SimpleNamespace(
            name="Flex Room",
            serial="LR5-001",
            get_activities=AsyncMock(return_value=[]),
            reassign_pet_visit=AsyncMock(return_value={}),
        )
        session = SimpleNamespace(
            request=AsyncMock(return_value={"isReassigned": True})
        )
        account = SimpleNamespace(robots=[robot], pets=[jane, sterling], session=session)
        lr_coordinator = SimpleNamespace(
            account=account,
            async_request_refresh=AsyncMock(),
        )
        hass = self._make_hass(account, lr_coordinator)

        # Reassign
        res = await api.async_reassign_visit(
            hass, event_id="evt-10", from_pet="Jane", to_pet="Sterling"
        )
        self.assertEqual(res["action"], "reassign")
        session.request.assert_awaited_with(
            "PATCH",
            f"{api.LR5_ENDPOINT}/robots/LR5-001/activities",
            json={"eventId": "evt-10", "fromPetId": "PET-JANE", "toPetId": "PET-STERLING"},
        )
        lr_coordinator.async_request_refresh.assert_awaited_once()

        # Unassign
        res_un = await api.async_reassign_visit(
            hass, event_id="evt-11", from_pet="Jane", refresh=False
        )
        self.assertEqual(res_un["action"], "unassign")
        session.request.assert_awaited_with(
            "PATCH",
            f"{api.LR5_ENDPOINT}/robots/LR5-001/activities",
            json={"eventId": "evt-11", "fromPetId": "PET-JANE"},
        )

        # HTTP error surfaces cleanly as HomeAssistantError
        session.request = AsyncMock(side_effect=ClientResponseError(400, "Expired"))
        with self.assertRaises(HomeAssistantError):
            await api.async_reassign_visit(
                hass, event_id="evt-12", from_pet="Jane", to_pet="Sterling"
            )

    async def test_fetch_camera_videos_pagination_and_timezone(self) -> None:
        calls = []

        async def fake_get(url: str, headers: dict, params: dict):
            calls.append((url, headers, params))
            if params["page"] == "1":
                return [{"id": 101}, {"id": 102}]
            if params["page"] == "2":
                return [{"id": 102}]  # duplicate triggers stop
            return []

        account = SimpleNamespace(session=SimpleNamespace(get=fake_get))
        robot = SimpleNamespace(camera_metadata={"deviceId": "cam-xyz"})

        clips = await api.async_fetch_camera_videos(
            account, robot, "America/Chicago", date_str="2026-11-24", limit=50
        )
        self.assertEqual([c["id"] for c in clips], [101, 102])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][2], {"page": "1", "timezone": "America/Chicago"})
        self.assertIn("x-api-key", calls[0][1])
        self.assertTrue(calls[0][0].endswith("/cameras/cam-xyz/videos/2026-11-24"))


if __name__ == "__main__":
    unittest.main()
