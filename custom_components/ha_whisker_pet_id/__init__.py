"""HA Whisker Pet ID custom integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import (
    async_get_clip_urls,
    async_get_pets_summary,
    async_list_visits,
    async_reassign_visit,
)
from .const import (
    DOMAIN,
    SERVICE_GET_CLIP_URLS,
    SERVICE_GET_PETS,
    SERVICE_LIST_VISITS,
    SERVICE_REASSIGN_VISIT,
)
from .coordinator import WhiskerPetIdCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

GET_PETS_SCHEMA = vol.Schema(
    {
        vol.Optional("refresh", default=False): cv.boolean,
    }
)

LIST_VISITS_SCHEMA = vol.Schema(
    {
        vol.Optional("robot"): cv.string,
        vol.Optional("limit", default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=250)),
        vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("activity_type", default="PET_VISIT"): cv.string,
        vol.Optional("date"): cv.string,
        vol.Optional("include_clips", default=True): cv.boolean,
        vol.Optional("max_clip_delta_seconds", default=180): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1800)
        ),
    }
)

GET_CLIP_URLS_SCHEMA = vol.Schema(
    {
        vol.Required("clip_id"): cv.string,
        vol.Optional("robot"): cv.string,
    }
)

REASSIGN_VISIT_SCHEMA = vol.Schema(
    {
        vol.Required("event_id"): cv.string,
        vol.Optional("from_pet"): cv.string,
        vol.Optional("to_pet"): cv.string,
        vol.Optional("robot"): cv.string,
        vol.Optional("refresh", default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register HA Whisker Pet ID response-returning service actions."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_get_pets(call: ServiceCall) -> ServiceResponse:
        return await async_get_pets_summary(
            hass,
            refresh=bool(call.data.get("refresh", False)),
        )

    async def handle_list_visits(call: ServiceCall) -> ServiceResponse:
        return await async_list_visits(
            hass,
            robot_id=call.data.get("robot"),
            limit=int(call.data.get("limit", 50)),
            offset=int(call.data.get("offset", 0)),
            activity_type=call.data.get("activity_type", "PET_VISIT"),
            date_str=call.data.get("date"),
            include_clips=bool(call.data.get("include_clips", True)),
            max_clip_delta_seconds=int(call.data.get("max_clip_delta_seconds", 180)),
        )

    async def handle_get_clip_urls(call: ServiceCall) -> ServiceResponse:
        return await async_get_clip_urls(
            hass,
            clip_id=call.data["clip_id"],
            robot_id=call.data.get("robot"),
        )

    async def handle_reassign_visit(call: ServiceCall) -> ServiceResponse:
        result = await async_reassign_visit(
            hass,
            event_id=call.data["event_id"],
            from_pet=call.data.get("from_pet"),
            to_pet=call.data.get("to_pet"),
            robot_id=call.data.get("robot"),
            refresh=bool(call.data.get("refresh", True)),
        )
        if call.data.get("refresh", True):
            for coordinator in hass.data.get(DOMAIN, {}).values():
                if isinstance(coordinator, WhiskerPetIdCoordinator):
                    await coordinator.async_request_refresh()
        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PETS,
        handle_get_pets,
        schema=GET_PETS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_VISITS,
        handle_list_visits,
        schema=LIST_VISITS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CLIP_URLS,
        handle_get_clip_urls,
        schema=GET_CLIP_URLS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REASSIGN_VISIT,
        handle_reassign_visit,
        schema=REASSIGN_VISIT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Whisker Pet ID from a config entry."""
    coordinator = WhiskerPetIdCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
