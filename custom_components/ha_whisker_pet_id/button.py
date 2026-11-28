"""Button platform for HA Whisker Pet ID on-demand actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AUTO_PET_ID_MAX_PER_RUN,
    DEFAULT_AUTO_PET_ID_MAX_PER_RUN,
    DOMAIN,
)
from .coordinator import WhiskerPetIdCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HA Whisker Pet ID button entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    diag_coordinator: WhiskerPetIdCoordinator = runtime["diagnostics"]
    async_add_entities([WhiskerFixPetIdButton(diag_coordinator, entry)])


class WhiskerFixPetIdButton(
    CoordinatorEntity[WhiskerPetIdCoordinator], ButtonEntity
):
    """Button entity to trigger Hybrid + Gemini Pet ID mismatch fixing on demand."""

    _attr_has_entity_name = True
    _attr_translation_key = "fix_pet_id_mismatches"
    _attr_icon = "mdi:auto-fix"

    def __init__(
        self, coordinator: WhiskerPetIdCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the Fix Pet ID mismatches button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_fix_pet_id_mismatches"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="HA Whisker Pet ID",
            manufacturer="Whisker",
            model="Litter-Robot 5 Pet ID",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        """Run Hybrid + Gemini verification & auto-reassignment on recent flagged visits."""
        limit = max(
            5,
            int(
                self.coordinator.option(
                    CONF_AUTO_PET_ID_MAX_PER_RUN,
                    DEFAULT_AUTO_PET_ID_MAX_PER_RUN,
                )
            ),
        )
        await self.coordinator.async_verify_visits_with_ai(
            trigger="service",
            dry_run=False,
            limit=limit,
            retry_unreassigned=True,
        )
        await self.coordinator.async_request_refresh()
