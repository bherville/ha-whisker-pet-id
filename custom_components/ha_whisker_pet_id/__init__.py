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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import (
    async_get_clip_urls,
    async_get_pets_summary,
    async_list_visits,
    async_reassign_visit,
)
from .const import (
    AUTO_PET_ID_CONFIDENCE_LEVELS,
    AUTO_PET_ID_MODES,
    AUTO_PET_ID_NOTIFY_MODES,
    CONF_AI_TASK_ENTITY,
    CONF_ALERT_COOLDOWN_HOURS,
    CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS,
    CONF_AUTO_PET_ID_MAX_PER_RUN,
    CONF_AUTO_PET_ID_MIN_CONFIDENCE,
    CONF_AUTO_PET_ID_MODE,
    CONF_AUTO_PET_ID_NOTIFY,
    CONF_AUTO_UNASSIGN_SCALE_GLITCHES,
    CONF_CLUSTER_MIN_VISITS,
    CONF_CLUSTER_WINDOW_MINUTES,
    CONF_ENABLE_DAILY_SUMMARY,
    CONF_ENABLE_HYBRID_FAST_PATH,
    CONF_ENABLE_PUSH_ALERTS,
    CONF_HEALTH_WINDOW_HOURS,
    CONF_NOTIFY_SERVICE,
    CONF_SUMMARY_HOUR,
    CONF_SUMMARY_MINUTE,
    CONF_VIDEO_ESCALATION,
    DEFAULT_MAX_CLIP_DELTA_SECONDS,
    DOMAIN,
    SERVICE_CONFIGURE_HEALTH,
    SERVICE_GENERATE_HEALTH_SUMMARY,
    SERVICE_GET_CLIP_URLS,
    SERVICE_GET_PETS,
    SERVICE_LIST_VISITS,
    SERVICE_REASSIGN_VISIT,
    SERVICE_VERIFY_VISITS_WITH_AI,
    VIDEO_ESCALATION_MODES,
)
from .coordinator import WhiskerHealthCoordinator, WhiskerPetIdCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]
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
        vol.Optional("max_clip_delta_seconds", default=DEFAULT_MAX_CLIP_DELTA_SECONDS): vol.All(
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

GENERATE_HEALTH_SUMMARY_SCHEMA = vol.Schema(
    {
        vol.Optional("hours"): vol.All(vol.Coerce(int), vol.Range(min=12, max=168)),
        vol.Optional("ai_task_entity"): cv.string,
        vol.Optional("use_ai", default=True): cv.boolean,
        vol.Optional("notify", default=False): cv.boolean,
        vol.Optional("notify_service"): cv.string,
        vol.Optional("robot"): cv.string,
    }
)

CONFIGURE_HEALTH_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_AI_TASK_ENTITY): cv.string,
        vol.Optional(CONF_NOTIFY_SERVICE): cv.string,
        vol.Optional(CONF_ENABLE_DAILY_SUMMARY): cv.boolean,
        vol.Optional(CONF_SUMMARY_HOUR): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
        vol.Optional(CONF_SUMMARY_MINUTE): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
        vol.Optional(CONF_ENABLE_PUSH_ALERTS): cv.boolean,
        vol.Optional(CONF_HEALTH_WINDOW_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=12, max=168)
        ),
        vol.Optional(CONF_CLUSTER_WINDOW_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=60)
        ),
        vol.Optional(CONF_CLUSTER_MIN_VISITS): vol.All(
            vol.Coerce(int), vol.Range(min=2, max=10)
        ),
        vol.Optional(CONF_ALERT_COOLDOWN_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=48)
        ),
        vol.Optional(CONF_AUTO_PET_ID_MODE): vol.In(AUTO_PET_ID_MODES),
        vol.Optional(CONF_ENABLE_HYBRID_FAST_PATH): cv.boolean,
        vol.Optional(CONF_VIDEO_ESCALATION): vol.In(VIDEO_ESCALATION_MODES),
        vol.Optional(CONF_AUTO_PET_ID_MIN_CONFIDENCE): vol.In(AUTO_PET_ID_CONFIDENCE_LEVELS),
        vol.Optional(CONF_AUTO_UNASSIGN_SCALE_GLITCHES): cv.boolean,
        vol.Optional(CONF_AUTO_PET_ID_NOTIFY): vol.In(AUTO_PET_ID_NOTIFY_MODES),
        vol.Optional(CONF_AUTO_PET_ID_MAX_PER_RUN): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=15)
        ),
        vol.Optional(CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS): vol.All(
            vol.Coerce(int), vol.Range(min=30, max=300)
        ),
    }
)

VERIFY_VISITS_WITH_AI_SCHEMA = vol.Schema(
    {
        vol.Optional("event_id"): cv.string,
        vol.Optional("dry_run"): cv.boolean,
        vol.Optional("limit", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=25)),
        vol.Optional("video_escalation"): vol.In(VIDEO_ESCALATION_MODES),
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("robot"): cv.string,
    }
)


def _iter_coordinators(
    hass: HomeAssistant,
) -> tuple[list[WhiskerPetIdCoordinator], list[WhiskerHealthCoordinator]]:
    diag_list: list[WhiskerPetIdCoordinator] = []
    health_list: list[WhiskerHealthCoordinator] = []
    for item in hass.data.get(DOMAIN, {}).values():
        if isinstance(item, dict):
            if isinstance(item.get("diagnostics"), WhiskerPetIdCoordinator):
                diag_list.append(item["diagnostics"])
            if isinstance(item.get("health"), WhiskerHealthCoordinator):
                health_list.append(item["health"])
        elif isinstance(item, WhiskerPetIdCoordinator):
            diag_list.append(item)
    return diag_list, health_list


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register HA Whisker Pet ID service actions."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_get_pets(call: ServiceCall) -> ServiceResponse:
        return await async_get_pets_summary(
            hass,
            refresh=bool(call.data.get("refresh", False)),
        )

    async def handle_list_visits(call: ServiceCall) -> ServiceResponse:
        diag_list, _ = _iter_coordinators(hass)
        baselines = diag_list[0]._clean_baselines if diag_list else None
        return await async_list_visits(
            hass,
            robot_id=call.data.get("robot"),
            limit=int(call.data.get("limit", 50)),
            offset=int(call.data.get("offset", 0)),
            activity_type=call.data.get("activity_type", "PET_VISIT"),
            date_str=call.data.get("date"),
            include_clips=bool(call.data.get("include_clips", True)),
            max_clip_delta_seconds=int(
                call.data.get("max_clip_delta_seconds", DEFAULT_MAX_CLIP_DELTA_SECONDS)
            ),
            baseline_overrides=baselines or None,
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
            diag_list, _ = _iter_coordinators(hass)
            for coordinator in diag_list:
                await coordinator.async_request_refresh()
        return result

    async def handle_generate_health_summary(call: ServiceCall) -> ServiceResponse:
        _, health_list = _iter_coordinators(hass)
        if not health_list:
            raise HomeAssistantError(
                "HA Whisker Pet ID is not configured yet. Add the integration first."
            )
        health_coord = health_list[0]
        return await health_coord.async_run_health_summary(
            trigger="service",
            use_ai=bool(call.data.get("use_ai", True)),
            notify=bool(call.data.get("notify", False)),
            window_hours=call.data.get("hours"),
            ai_task_entity=call.data.get("ai_task_entity"),
            notify_service=call.data.get("notify_service"),
            robot_id=call.data.get("robot"),
        )

    async def handle_configure_health(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError(
                "HA Whisker Pet ID is not configured yet. Add the integration first."
            )
        entry = entries[0]
        updated_options = {**entry.options, **dict(call.data)}
        hass.config_entries.async_update_entry(entry, options=updated_options)
        return {
            "success": True,
            "entry_id": entry.entry_id,
            "options": updated_options,
        }

    async def handle_verify_visits_with_ai(call: ServiceCall) -> ServiceResponse:
        diag_list, _ = _iter_coordinators(hass)
        if not diag_list:
            raise HomeAssistantError(
                "HA Whisker Pet ID is not configured yet. Add the integration first."
            )
        return await diag_list[0].async_verify_visits_with_ai(
            trigger="service",
            event_id=call.data.get("event_id"),
            dry_run=call.data.get("dry_run"),
            limit=int(call.data.get("limit", 5)),
            video_escalation=call.data.get("video_escalation"),
            force=bool(call.data.get("force", False)),
            robot_id=call.data.get("robot"),
        )

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_HEALTH_SUMMARY,
        handle_generate_health_summary,
        schema=GENERATE_HEALTH_SUMMARY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIGURE_HEALTH,
        handle_configure_health,
        schema=CONFIGURE_HEALTH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_VERIFY_VISITS_WITH_AI,
        handle_verify_visits_with_ai,
        schema=VERIFY_VISITS_WITH_AI_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Whisker Pet ID from a config entry."""
    health_coordinator = WhiskerHealthCoordinator(hass, entry)
    await health_coordinator.async_config_entry_first_refresh()
    health_coordinator.start_schedule()

    diag_coordinator = WhiskerPetIdCoordinator(hass, entry)
    await diag_coordinator.async_load_store()
    diag_coordinator.attach_health_coordinator(health_coordinator)
    await diag_coordinator.async_config_entry_first_refresh()
    diag_coordinator.start_reactive_listener()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "diagnostics": diag_coordinator,
        "health": health_coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(runtime, dict):
        if isinstance(runtime.get("health"), WhiskerHealthCoordinator):
            runtime["health"].stop_schedule()
        if isinstance(runtime.get("diagnostics"), WhiskerPetIdCoordinator):
            runtime["diagnostics"].stop_reactive_listener()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
