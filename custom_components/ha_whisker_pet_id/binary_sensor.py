"""Binary sensor platform for HA Whisker Pet ID health alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WhiskerHealthCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HA Whisker Pet ID binary sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    health_coordinator: WhiskerHealthCoordinator = runtime["health"]
    async_add_entities([WhiskerHealthAlertBinarySensor(health_coordinator, entry)])


class WhiskerHealthAlertBinarySensor(
    CoordinatorEntity[WhiskerHealthCoordinator], BinarySensorEntity
):
    """Problem binary sensor raised on watch/alert status or visit clustering."""

    _attr_has_entity_name = True
    _attr_translation_key = "health_alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: WhiskerHealthCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize health alert binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_health_alert"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="HA Whisker Pet ID",
            manufacturer="Whisker",
            model="Litter-Robot 5 Pet ID",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        """Return True if overall status is watch/alert or clusters are present."""
        data = self.coordinator.data or {}
        return (
            data.get("overall_status") in ("watch", "alert")
            or int(data.get("clusters_detected", 0)) > 0
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return alert details and active visit clusters."""
        data = self.coordinator.data or {}
        if not data:
            return {}
        return {
            "overall_status": data.get("overall_status"),
            "headline": data.get("headline"),
            "alert_pets": data.get("alert_pets", []),
            "alert_message": data.get("alert_message", ""),
            "clusters_detected": data.get("clusters_detected", 0),
            "clusters": data.get("clusters", []),
            "last_generated_at": data.get("last_generated_at"),
        }
