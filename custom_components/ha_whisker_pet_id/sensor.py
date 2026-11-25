"""Diagnostic sensor platform for HA Whisker Pet ID."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WhiskerPetIdCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HA Whisker Pet ID sensors from a config entry."""
    coordinator: WhiskerPetIdCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WhiskerFlaggedVisitsSensor(coordinator, entry)])


class WhiskerFlaggedVisitsSensor(
    CoordinatorEntity[WhiskerPetIdCoordinator], SensorEntity
):
    """Diagnostic sensor counting recently flagged LR5 Pet ID visits."""

    _attr_has_entity_name = True
    _attr_translation_key = "flagged_visits"
    _attr_icon = "mdi:cat"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: WhiskerPetIdCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the flagged visits sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_flagged_visits"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="HA Whisker Pet ID",
            manufacturer="Whisker",
            model="Litter-Robot 5 Pet ID",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int:
        """Return the number of flagged visits in the recent window."""
        if not self.coordinator.data:
            return 0
        return int(self.coordinator.data.get("flagged_count", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return breakdown counts and compact flagged visit summaries."""
        if not self.coordinator.data:
            return {}
        return {
            "robot": self.coordinator.data.get("robot"),
            "serial": self.coordinator.data.get("serial"),
            "total_visits_checked": self.coordinator.data.get("total_visits_checked", 0),
            "unassigned_count": self.coordinator.data.get("unassigned_count", 0),
            "weight_mismatch_count": self.coordinator.data.get("weight_mismatch_count", 0),
            "scale_anomaly_count": self.coordinator.data.get("scale_anomaly_count", 0),
            "flagged_visits": self.coordinator.data.get("flagged_visits", []),
        }
