"""Config flow and options flow for HA Whisker Pet ID."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .api import get_litterrobot_runtime, get_lr5_robots
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
    CONF_MAX_VALID_WEIGHT_LBS,
    CONF_MIN_VALID_WEIGHT_LBS,
    CONF_NOTIFY_SERVICE,
    CONF_ROBOT,
    CONF_SNAPSHOT_CAMERA_ENTITY,
    CONF_SNAPSHOT_MAX_FILES,
    CONF_SUMMARY_HOUR,
    CONF_SUMMARY_MINUTE,
    CONF_VIDEO_ESCALATION,
    CONF_WEIGHT_MISMATCH_LBS,
    DEFAULT_AI_TASK_ENTITY,
    DEFAULT_ALERT_COOLDOWN_HOURS,
    DEFAULT_AUTO_PET_ID_CLIP_DELAY_SECONDS,
    DEFAULT_AUTO_PET_ID_MAX_PER_RUN,
    DEFAULT_AUTO_PET_ID_MIN_CONFIDENCE,
    DEFAULT_AUTO_PET_ID_MODE,
    DEFAULT_AUTO_PET_ID_NOTIFY,
    DEFAULT_AUTO_UNASSIGN_SCALE_GLITCHES,
    DEFAULT_CLUSTER_MIN_VISITS,
    DEFAULT_CLUSTER_WINDOW_MINUTES,
    DEFAULT_ENABLE_DAILY_SUMMARY,
    DEFAULT_ENABLE_HYBRID_FAST_PATH,
    DEFAULT_ENABLE_PUSH_ALERTS,
    DEFAULT_HEALTH_WINDOW_HOURS,
    DEFAULT_MAX_VALID_WEIGHT_LBS,
    DEFAULT_MIN_VALID_WEIGHT_LBS,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_ROBOT,
    DEFAULT_SNAPSHOT_CAMERA_ENTITY,
    DEFAULT_SUMMARY_HOUR,
    DEFAULT_SUMMARY_MINUTE,
    DEFAULT_VIDEO_ESCALATION,
    DEFAULT_WEIGHT_MISMATCH_LBS,
    DOMAIN,
    SNAPSHOT_MAX_FILES,
    VIDEO_ESCALATION_MODES,
)


def _discover_lr5_robot_options(hass: Any) -> list[selector.SelectOptionDict]:
    """Return SelectOptionDict items for discovered Litter-Robot 5 units."""
    try:
        _, _, account = get_litterrobot_runtime(hass)
        robots = get_lr5_robots(account)
    except Exception:
        return []

    options: list[selector.SelectOptionDict] = []
    for robot in robots:
        serial = str(getattr(robot, "serial", "") or "").strip()
        name = str(getattr(robot, "name", "") or serial or "Litter-Robot").strip()
        if serial:
            options.append(
                selector.SelectOptionDict(value=serial, label=f"{name} ({serial})")
            )
    return options


def _optional_suggested(key: str, suggested: Any) -> vol.Optional:
    """Build a vol.Optional field with suggested_value only when non-empty."""
    if suggested not in (None, ""):
        return vol.Optional(key, description={"suggested_value": suggested})
    return vol.Optional(key)


class WhiskerPetIdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Whisker Pet ID."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WhiskerPetIdOptionsFlowHandler:
        """Return the options flow handler."""
        return WhiskerPetIdOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm setup using the loaded Whisker (litterrobot) integration."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        robot_options = _discover_lr5_robot_options(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _, _, account = get_litterrobot_runtime(self.hass)
                lr5_robots = get_lr5_robots(account)
            except HomeAssistantError:
                errors["base"] = "no_litterrobot_lr5"
            else:
                if not lr5_robots:
                    errors["base"] = "no_litterrobot_lr5"
                else:
                    await self.async_set_unique_id(DOMAIN)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="HA Whisker Pet ID",
                        data={},
                        options={
                            CONF_ROBOT: str(user_input.get(CONF_ROBOT) or "").strip(),
                            CONF_AI_TASK_ENTITY: str(
                                user_input.get(CONF_AI_TASK_ENTITY) or DEFAULT_AI_TASK_ENTITY
                            ).strip(),
                            CONF_NOTIFY_SERVICE: str(
                                user_input.get(CONF_NOTIFY_SERVICE) or DEFAULT_NOTIFY_SERVICE
                            ).strip(),
                            CONF_SNAPSHOT_CAMERA_ENTITY: str(
                                user_input.get(CONF_SNAPSHOT_CAMERA_ENTITY)
                                or DEFAULT_SNAPSHOT_CAMERA_ENTITY
                            ).strip(),
                            CONF_SNAPSHOT_MAX_FILES: SNAPSHOT_MAX_FILES,
                            CONF_MIN_VALID_WEIGHT_LBS: DEFAULT_MIN_VALID_WEIGHT_LBS,
                            CONF_MAX_VALID_WEIGHT_LBS: DEFAULT_MAX_VALID_WEIGHT_LBS,
                            CONF_WEIGHT_MISMATCH_LBS: DEFAULT_WEIGHT_MISMATCH_LBS,
                            CONF_ENABLE_DAILY_SUMMARY: DEFAULT_ENABLE_DAILY_SUMMARY,
                            CONF_SUMMARY_HOUR: DEFAULT_SUMMARY_HOUR,
                            CONF_SUMMARY_MINUTE: DEFAULT_SUMMARY_MINUTE,
                            CONF_ENABLE_PUSH_ALERTS: DEFAULT_ENABLE_PUSH_ALERTS,
                            CONF_HEALTH_WINDOW_HOURS: DEFAULT_HEALTH_WINDOW_HOURS,
                            CONF_CLUSTER_WINDOW_MINUTES: DEFAULT_CLUSTER_WINDOW_MINUTES,
                            CONF_CLUSTER_MIN_VISITS: DEFAULT_CLUSTER_MIN_VISITS,
                            CONF_ALERT_COOLDOWN_HOURS: DEFAULT_ALERT_COOLDOWN_HOURS,
                            CONF_AUTO_PET_ID_MODE: DEFAULT_AUTO_PET_ID_MODE,
                            CONF_ENABLE_HYBRID_FAST_PATH: DEFAULT_ENABLE_HYBRID_FAST_PATH,
                            CONF_VIDEO_ESCALATION: DEFAULT_VIDEO_ESCALATION,
                            CONF_AUTO_PET_ID_MIN_CONFIDENCE: DEFAULT_AUTO_PET_ID_MIN_CONFIDENCE,
                            CONF_AUTO_UNASSIGN_SCALE_GLITCHES: DEFAULT_AUTO_UNASSIGN_SCALE_GLITCHES,
                            CONF_AUTO_PET_ID_NOTIFY: DEFAULT_AUTO_PET_ID_NOTIFY,
                            CONF_AUTO_PET_ID_MAX_PER_RUN: DEFAULT_AUTO_PET_ID_MAX_PER_RUN,
                            CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS: DEFAULT_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                        },
                    )

        ai_entities = sorted(self.hass.states.async_entity_ids("ai_task"))
        suggested_ai = ai_entities[0] if ai_entities else ""

        fields: dict[Any, Any] = {}
        if len(robot_options) > 1:
            fields[vol.Required(CONF_ROBOT, default=robot_options[0]["value"])] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=robot_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
            )
        elif robot_options:
            fields[
                _optional_suggested(CONF_ROBOT, robot_options[0]["value"])
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=robot_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        else:
            fields[vol.Optional(CONF_ROBOT)] = selector.TextSelector()

        fields[_optional_suggested(CONF_AI_TASK_ENTITY, suggested_ai)] = (
            selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task"))
        )
        fields[vol.Optional(CONF_NOTIFY_SERVICE)] = selector.TextSelector()
        fields[vol.Optional(CONF_SNAPSHOT_CAMERA_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="camera")
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(fields),
            errors=errors,
        )


class WhiskerPetIdOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for configuring AI health summaries and Auto-Pet-ID."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage robot target, AI health schedule, push alerts, weights, and Auto-Pet-ID options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            min_w = float(
                user_input.get(CONF_MIN_VALID_WEIGHT_LBS, DEFAULT_MIN_VALID_WEIGHT_LBS)
            )
            max_w = float(
                user_input.get(CONF_MAX_VALID_WEIGHT_LBS, DEFAULT_MAX_VALID_WEIGHT_LBS)
            )
            if min_w >= max_w:
                errors["base"] = "invalid_weight_bounds"
            else:
                cleaned = dict(user_input)
                for str_key in (
                    CONF_ROBOT,
                    CONF_AI_TASK_ENTITY,
                    CONF_NOTIFY_SERVICE,
                    CONF_SNAPSHOT_CAMERA_ENTITY,
                ):
                    cleaned[str_key] = str(cleaned.get(str_key) or "").strip()
                return self.async_create_entry(title="", data=cleaned)

        opts = user_input if user_input is not None else self.config_entry.options
        robot_options = _discover_lr5_robot_options(self.hass)
        robot_field_selector: Any = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=robot_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
            if robot_options
            else selector.TextSelector()
        )

        schema = vol.Schema(
            {
                _optional_suggested(
                    CONF_ROBOT, opts.get(CONF_ROBOT, DEFAULT_ROBOT)
                ): robot_field_selector,
                _optional_suggested(
                    CONF_AI_TASK_ENTITY,
                    opts.get(CONF_AI_TASK_ENTITY, DEFAULT_AI_TASK_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="ai_task")
                ),
                _optional_suggested(
                    CONF_NOTIFY_SERVICE,
                    opts.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
                ): selector.TextSelector(),
                _optional_suggested(
                    CONF_SNAPSHOT_CAMERA_ENTITY,
                    opts.get(
                        CONF_SNAPSHOT_CAMERA_ENTITY, DEFAULT_SNAPSHOT_CAMERA_ENTITY
                    ),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="camera")
                ),
                vol.Optional(
                    CONF_SNAPSHOT_MAX_FILES,
                    default=int(opts.get(CONF_SNAPSHOT_MAX_FILES, SNAPSHOT_MAX_FILES)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=500,
                        step=10,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_MIN_VALID_WEIGHT_LBS,
                    default=float(
                        opts.get(CONF_MIN_VALID_WEIGHT_LBS, DEFAULT_MIN_VALID_WEIGHT_LBS)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0,
                        max=10.0,
                        step=0.5,
                        unit_of_measurement="lb",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_MAX_VALID_WEIGHT_LBS,
                    default=float(
                        opts.get(CONF_MAX_VALID_WEIGHT_LBS, DEFAULT_MAX_VALID_WEIGHT_LBS)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10.0,
                        max=40.0,
                        step=0.5,
                        unit_of_measurement="lb",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_WEIGHT_MISMATCH_LBS,
                    default=float(
                        opts.get(CONF_WEIGHT_MISMATCH_LBS, DEFAULT_WEIGHT_MISMATCH_LBS)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.25,
                        max=5.0,
                        step=0.05,
                        unit_of_measurement="lb",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_AUTO_PET_ID_MODE,
                    default=opts.get(CONF_AUTO_PET_ID_MODE, DEFAULT_AUTO_PET_ID_MODE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(AUTO_PET_ID_MODES),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_ENABLE_HYBRID_FAST_PATH,
                    default=opts.get(
                        CONF_ENABLE_HYBRID_FAST_PATH, DEFAULT_ENABLE_HYBRID_FAST_PATH
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_VIDEO_ESCALATION,
                    default=opts.get(CONF_VIDEO_ESCALATION, DEFAULT_VIDEO_ESCALATION),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(VIDEO_ESCALATION_MODES),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_AUTO_PET_ID_MIN_CONFIDENCE,
                    default=opts.get(
                        CONF_AUTO_PET_ID_MIN_CONFIDENCE,
                        DEFAULT_AUTO_PET_ID_MIN_CONFIDENCE,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(AUTO_PET_ID_CONFIDENCE_LEVELS),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_AUTO_UNASSIGN_SCALE_GLITCHES,
                    default=opts.get(
                        CONF_AUTO_UNASSIGN_SCALE_GLITCHES,
                        DEFAULT_AUTO_UNASSIGN_SCALE_GLITCHES,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_AUTO_PET_ID_NOTIFY,
                    default=opts.get(
                        CONF_AUTO_PET_ID_NOTIFY, DEFAULT_AUTO_PET_ID_NOTIFY
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(AUTO_PET_ID_NOTIFY_MODES),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_AUTO_PET_ID_MAX_PER_RUN,
                    default=opts.get(
                        CONF_AUTO_PET_ID_MAX_PER_RUN, DEFAULT_AUTO_PET_ID_MAX_PER_RUN
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=15)),
                vol.Optional(
                    CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                    default=opts.get(
                        CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                        DEFAULT_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
                vol.Optional(
                    CONF_ENABLE_DAILY_SUMMARY,
                    default=opts.get(
                        CONF_ENABLE_DAILY_SUMMARY, DEFAULT_ENABLE_DAILY_SUMMARY
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_SUMMARY_HOUR,
                    default=opts.get(CONF_SUMMARY_HOUR, DEFAULT_SUMMARY_HOUR),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Optional(
                    CONF_SUMMARY_MINUTE,
                    default=opts.get(CONF_SUMMARY_MINUTE, DEFAULT_SUMMARY_MINUTE),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
                vol.Optional(
                    CONF_ENABLE_PUSH_ALERTS,
                    default=opts.get(
                        CONF_ENABLE_PUSH_ALERTS, DEFAULT_ENABLE_PUSH_ALERTS
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_HEALTH_WINDOW_HOURS,
                    default=opts.get(
                        CONF_HEALTH_WINDOW_HOURS, DEFAULT_HEALTH_WINDOW_HOURS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=12, max=168)),
                vol.Optional(
                    CONF_CLUSTER_WINDOW_MINUTES,
                    default=opts.get(
                        CONF_CLUSTER_WINDOW_MINUTES, DEFAULT_CLUSTER_WINDOW_MINUTES
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                vol.Optional(
                    CONF_CLUSTER_MIN_VISITS,
                    default=opts.get(
                        CONF_CLUSTER_MIN_VISITS, DEFAULT_CLUSTER_MIN_VISITS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=2, max=10)),
                vol.Optional(
                    CONF_ALERT_COOLDOWN_HOURS,
                    default=opts.get(
                        CONF_ALERT_COOLDOWN_HOURS, DEFAULT_ALERT_COOLDOWN_HOURS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=48)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
