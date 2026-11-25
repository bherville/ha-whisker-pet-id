"""Config flow for HA Whisker Pet ID."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import get_litterrobot_runtime, get_lr5_robots
from .const import DOMAIN


class WhiskerPetIdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Whisker Pet ID."""

    VERSION = 1

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
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=errors,
        )
