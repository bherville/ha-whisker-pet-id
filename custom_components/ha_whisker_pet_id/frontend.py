"""Frontend static resource & Lovelace card registration for HA Whisker Pet ID."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN, FRONTEND_SCRIPT_URL, INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)
_REGISTERED_KEY = "frontend_cards_registered"
_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
_CARDS_JS_PATH = _FRONTEND_DIR / "ha-whisker-pet-id-cards.js"


async def async_register_frontend_cards(hass: HomeAssistant) -> bool:
    """Serve built-in Lovelace custom cards and register the module URL idempotently."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_REGISTERED_KEY):
        return False

    if not _CARDS_JS_PATH.is_file():
        _LOGGER.warning("Whisker Pet ID card script missing at %s", _CARDS_JS_PATH)
        return False

    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig
    except ImportError:
        _LOGGER.debug(
            "Home Assistant frontend/http components unavailable; skipping card registration"
        )
        return False

    http = getattr(hass, "http", None)
    if http is None:
        _LOGGER.debug("hass.http not initialized; skipping card registration")
        return False

    await http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_SCRIPT_URL,
                str(_CARDS_JS_PATH),
                cache_headers=False,
            )
        ]
    )
    add_extra_js_url(hass, f"{FRONTEND_SCRIPT_URL}?v={INTEGRATION_VERSION}")
    domain_data[_REGISTERED_KEY] = True
    _LOGGER.debug(
        "Registered Whisker Pet ID Lovelace cards at %s?v=%s",
        FRONTEND_SCRIPT_URL,
        INTEGRATION_VERSION,
    )
    return True
