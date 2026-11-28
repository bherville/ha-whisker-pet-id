"""Tests for the HA Whisker Pet ID button platform."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "custom_components" / "ha_whisker_pet_id"


def _load_button_module():
    """Load button.py inside isolated HA/coordinator sys.modules stubs."""
    added_or_existing = {}

    if "homeassistant" not in sys.modules:
        added_or_existing["homeassistant"] = types.ModuleType("homeassistant")
    if "homeassistant.config_entries" not in sys.modules:
        ha_ce = types.ModuleType("homeassistant.config_entries")
        ha_ce.ConfigEntry = MagicMock
        added_or_existing["homeassistant.config_entries"] = ha_ce
    if "homeassistant.core" not in sys.modules:
        ha_core = types.ModuleType("homeassistant.core")
        ha_core.HomeAssistant = type("HomeAssistant", (), {})
        added_or_existing["homeassistant.core"] = ha_core
    if "homeassistant.components" not in sys.modules:
        added_or_existing["homeassistant.components"] = types.ModuleType(
            "homeassistant.components"
        )
    if "homeassistant.helpers" not in sys.modules:
        added_or_existing["homeassistant.helpers"] = types.ModuleType(
            "homeassistant.helpers"
        )
    if "custom_components" not in sys.modules:
        cc = types.ModuleType("custom_components")
        cc.__path__ = [str(ROOT / "custom_components")]
        added_or_existing["custom_components"] = cc
    if "custom_components.ha_whisker_pet_id" not in sys.modules:
        pkg = types.ModuleType("custom_components.ha_whisker_pet_id")
        pkg.__path__ = [str(PKG_DIR)]
        added_or_existing["custom_components.ha_whisker_pet_id"] = pkg

    for k, mod in added_or_existing.items():
        sys.modules[k] = mod

    ha_btn = types.ModuleType("homeassistant.components.button")

    class ButtonEntity:  # noqa: D101
        pass

    ha_btn.ButtonEntity = ButtonEntity

    ha_dr = types.ModuleType("homeassistant.helpers.device_registry")

    class DeviceEntryType:
        SERVICE = "service"

    class DeviceInfo(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    ha_dr.DeviceEntryType = DeviceEntryType
    ha_dr.DeviceInfo = DeviceInfo

    ha_ep = types.ModuleType("homeassistant.helpers.entity_platform")
    ha_ep.AddEntitiesCallback = object

    ha_uc = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

    ha_uc.CoordinatorEntity = CoordinatorEntity

    coord_stub = types.ModuleType("custom_components.ha_whisker_pet_id.coordinator")

    class WhiskerPetIdCoordinator:  # noqa: D101
        pass

    coord_stub.WhiskerPetIdCoordinator = WhiskerPetIdCoordinator

    const_mod = importlib.import_module("custom_components.ha_whisker_pet_id.const")

    with patch.dict(
        sys.modules,
        {
            "homeassistant.components.button": ha_btn,
            "homeassistant.helpers.device_registry": ha_dr,
            "homeassistant.helpers.entity_platform": ha_ep,
            "homeassistant.helpers.update_coordinator": ha_uc,
            "custom_components.ha_whisker_pet_id.coordinator": coord_stub,
        },
    ):
        if "custom_components.ha_whisker_pet_id.button" in sys.modules:
            del sys.modules["custom_components.ha_whisker_pet_id.button"]
        btn_mod = importlib.import_module("custom_components.ha_whisker_pet_id.button")

    return btn_mod, const_mod


button, const = _load_button_module()


class TestFixPetIdButton(unittest.TestCase):
    """Verify Fix Pet ID mismatches button entity setup and async_press."""

    def test_setup_entry_and_press_triggers_gemini_fix(self) -> None:
        coordinator = MagicMock()
        coordinator.option = MagicMock(return_value=12)
        coordinator.async_verify_visits_with_ai = AsyncMock(return_value={"decisions": []})
        coordinator.async_request_refresh = AsyncMock()

        entry = MagicMock()
        entry.entry_id = "entry_123"

        hass = MagicMock()
        hass.data = {const.DOMAIN: {entry.entry_id: {"diagnostics": coordinator}}}

        added = []
        asyncio.run(button.async_setup_entry(hass, entry, added.extend))

        self.assertEqual(len(added), 1)
        entity = added[0]
        self.assertEqual(entity._attr_translation_key, "fix_pet_id_mismatches")
        self.assertEqual(entity._attr_icon, "mdi:auto-fix")
        self.assertEqual(entity._attr_unique_id, "entry_123_fix_pet_id_mismatches")

        asyncio.run(entity.async_press())

        coordinator.async_verify_visits_with_ai.assert_awaited_once_with(
            trigger="service",
            dry_run=False,
            limit=12,
            retry_unreassigned=True,
        )
        coordinator.async_request_refresh.assert_awaited_once()

    def test_retry_unreassigned_parameter_exists_in_coordinator(self) -> None:
        coord_src = (PKG_DIR / "coordinator.py").read_text(encoding="utf-8")
        self.assertIn("retry_unreassigned: bool = False", coord_src)
        self.assertIn("and not retry_unreassigned", coord_src)


if __name__ == "__main__":
    unittest.main()
