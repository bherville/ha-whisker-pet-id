"""Tests for built-in Lovelace card registration and dashboard YAML templates."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "custom_components" / "ha_whisker_pet_id"


def _ensure_ha_stubs() -> None:
    """Install minimal Home Assistant & package stubs for offline unit tests."""
    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    if "homeassistant.core" not in sys.modules:
        ha_core = types.ModuleType("homeassistant.core")

        class HomeAssistant:  # noqa: D101
            pass

        ha_core.HomeAssistant = HomeAssistant
        sys.modules["homeassistant.core"] = ha_core
    if "homeassistant.components" not in sys.modules:
        sys.modules["homeassistant.components"] = types.ModuleType(
            "homeassistant.components"
        )
    if "custom_components" not in sys.modules:
        cc = types.ModuleType("custom_components")
        cc.__path__ = [str(ROOT / "custom_components")]
        sys.modules["custom_components"] = cc
    if "custom_components.ha_whisker_pet_id" not in sys.modules:
        pkg = types.ModuleType("custom_components.ha_whisker_pet_id")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["custom_components.ha_whisker_pet_id"] = pkg


_ensure_ha_stubs()

from custom_components.ha_whisker_pet_id import const, frontend  # noqa: E402


class TestFrontendCards(unittest.TestCase):
    """Verify static JS bundle, idempotent card registration, and dashboard templates."""

    def test_cards_js_exists_and_registers_both_elements(self) -> None:
        js_path = PKG_DIR / "frontend" / "ha-whisker-pet-id-cards.js"
        self.assertTrue(js_path.is_file())
        content = js_path.read_text(encoding="utf-8")

        self.assertIn("whisker-health-archive-card", content)
        self.assertIn("whisker-auto-pet-id-card", content)
        self.assertIn("Smart Cat ID", content)
        self.assertIn("Auto-Fix On", content)
        self.assertIn("page_size", content)
        self.assertIn("getGridOptions", content)
        self.assertIn("@container", content)
        self.assertIn("window.customCards", content)
        self.assertIn("getStubConfig", content)
        self.assertIn("escapeHtml", content)
        self.assertIn(const.INTEGRATION_VERSION, content)

    def test_async_register_frontend_cards_and_idempotency(self) -> None:
        recorded_urls: list[str] = []

        ha_frontend = types.ModuleType("homeassistant.components.frontend")
        ha_frontend.add_extra_js_url = lambda hass, url, es5=False: recorded_urls.append(url)

        ha_http = types.ModuleType("homeassistant.components.http")

        class StaticPathConfig:
            def __init__(self, url_path: str, path: str, cache_headers: bool = True) -> None:
                self.url_path = url_path
                self.path = path
                self.cache_headers = cache_headers

        ha_http.StaticPathConfig = StaticPathConfig

        hass = MagicMock()
        hass.data = {}
        hass.http = MagicMock()
        hass.http.async_register_static_paths = AsyncMock()

        with patch.dict(
            sys.modules,
            {
                "homeassistant.components.frontend": ha_frontend,
                "homeassistant.components.http": ha_http,
            },
        ):
            first = asyncio.run(frontend.async_register_frontend_cards(hass))
            second = asyncio.run(frontend.async_register_frontend_cards(hass))

        self.assertTrue(first)
        self.assertFalse(second)
        hass.http.async_register_static_paths.assert_awaited_once()
        configs = hass.http.async_register_static_paths.call_args.args[0]
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].url_path, const.FRONTEND_SCRIPT_URL)
        self.assertTrue(configs[0].path.endswith("ha-whisker-pet-id-cards.js"))
        self.assertFalse(configs[0].cache_headers)
        self.assertEqual(
            recorded_urls,
            [f"{const.FRONTEND_SCRIPT_URL}?v={const.INTEGRATION_VERSION}"],
        )

    def test_async_register_frontend_cards_handles_missing_http(self) -> None:
        ha_frontend = types.ModuleType("homeassistant.components.frontend")
        ha_frontend.add_extra_js_url = lambda hass, url, es5=False: None
        ha_http = types.ModuleType("homeassistant.components.http")
        ha_http.StaticPathConfig = MagicMock()

        hass = MagicMock()
        hass.data = {}
        hass.http = None

        with patch.dict(
            sys.modules,
            {
                "homeassistant.components.frontend": ha_frontend,
                "homeassistant.components.http": ha_http,
            },
        ):
            result = asyncio.run(frontend.async_register_frontend_cards(hass))

        self.assertFalse(result)
        self.assertFalse(hass.data[const.DOMAIN].get("frontend_cards_registered", False))

    def test_dashboard_yaml_templates_parse_cleanly(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed in test environment")

        dashboards_dir = ROOT / "dashboards"
        expected = {
            "whisker_health_stack.yaml": "custom:whisker-health-archive-card",
            "whisker_auto_pet_id_stack.yaml": "custom:whisker-auto-pet-id-card",
            "cat_avatar_cards.yaml": "/local/ha_whisker_pet_id/pets/",
        }
        for filename, marker in expected.items():
            path = dashboards_dir / filename
            self.assertTrue(path.is_file(), f"Missing dashboard template {filename}")
            text = path.read_text(encoding="utf-8")
            self.assertIn(marker, text)
            parsed = yaml.safe_load(text)
            self.assertIsInstance(parsed, dict)
            self.assertIn("cards", parsed)
            self.assertGreaterEqual(len(parsed["cards"]), 2)


if __name__ == "__main__":
    unittest.main()
