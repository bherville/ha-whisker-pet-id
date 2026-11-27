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
    CONF_NOTIFY_SERVICE,
    CONF_SUMMARY_HOUR,
    CONF_SUMMARY_MINUTE,
    CONF_VIDEO_ESCALATION,
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
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_SUMMARY_HOUR,
    DEFAULT_SUMMARY_MINUTE,
    DEFAULT_VIDEO_ESCALATION,
    DOMAIN,
    VIDEO_ESCALATION_MODES,
)


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
                            CONF_AI_TASK_ENTITY: DEFAULT_AI_TASK_ENTITY,
                            CONF_NOTIFY_SERVICE: DEFAULT_NOTIFY_SERVICE,
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

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=errors,
        )


class WhiskerPetIdOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for configuring AI health summaries and Gemini Auto-Pet-ID."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage AI health summary schedule, push alerts, and Gemini Auto-Pet-ID options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AI_TASK_ENTITY,
                    default=opts.get(CONF_AI_TASK_ENTITY, DEFAULT_AI_TASK_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="ai_task")
                ),
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=opts.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
                ): selector.TextSelector(),
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
        return self.async_show_form(step_id="init", data_schema=schema)
