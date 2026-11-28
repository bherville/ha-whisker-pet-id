"""Unit tests for configuration defaults and localization/service parity."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import types
import unittest

import yaml


def _install_ha_stubs() -> None:
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
const = importlib.import_module("custom_components.ha_whisker_pet_id.const")

COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "ha_whisker_pet_id"
)


class TestDefaultsAndStringsParity(unittest.TestCase):
    """Ensure defaults are household-agnostic and strings/translations match."""

    def test_defaults_are_generic(self) -> None:
        self.assertEqual(const.DEFAULT_AI_TASK_ENTITY, "")
        self.assertEqual(const.DEFAULT_ROBOT, "")
        self.assertEqual(const.DEFAULT_NOTIFY_SERVICE, "")
        self.assertEqual(const.DEFAULT_SNAPSHOT_CAMERA_ENTITY, "")
        self.assertEqual(const.DEFAULT_MIN_VALID_WEIGHT_LBS, 3.0)
        self.assertEqual(const.DEFAULT_MAX_VALID_WEIGHT_LBS, 25.0)
        self.assertEqual(const.SNAPSHOT_MAX_FILES, 60)

    def test_strings_translations_and_services_parity(self) -> None:
        strings = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
        trans = json.loads(
            (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
        )
        self.assertEqual(strings, trans)

        services = yaml.safe_load((COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))
        self.assertEqual(set(services.keys()), set(strings["services"].keys()))
        cfg_fields = set(services["configure_health"]["fields"].keys())
        self.assertTrue(
            {
                const.CONF_ROBOT,
                const.CONF_AI_TASK_ENTITY,
                const.CONF_NOTIFY_SERVICE,
                const.CONF_SNAPSHOT_CAMERA_ENTITY,
                const.CONF_SNAPSHOT_MAX_FILES,
                const.CONF_MIN_VALID_WEIGHT_LBS,
                const.CONF_MAX_VALID_WEIGHT_LBS,
                const.CONF_WEIGHT_MISMATCH_LBS,
            }.issubset(cfg_fields)
        )
        opt_fields = set(strings["options"]["step"]["init"]["data"].keys())
        self.assertTrue(
            {
                const.CONF_ROBOT,
                const.CONF_SNAPSHOT_MAX_FILES,
                const.CONF_MIN_VALID_WEIGHT_LBS,
                const.CONF_MAX_VALID_WEIGHT_LBS,
                const.CONF_WEIGHT_MISMATCH_LBS,
            }.issubset(opt_fields)
        )
