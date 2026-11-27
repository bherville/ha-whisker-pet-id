"""Sensor platform for HA Whisker Pet ID diagnostics and Gemini health summaries."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alert_history import AlertHistoryManager
from .const import DOMAIN
from .coordinator import WhiskerHealthCoordinator, WhiskerPetIdCoordinator


def _service_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return shared DeviceInfo for the HA Whisker Pet ID service device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="HA Whisker Pet ID",
        manufacturer="Whisker",
        model="Litter-Robot 5 Pet ID",
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HA Whisker Pet ID sensors from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    diag_coordinator: WhiskerPetIdCoordinator = runtime["diagnostics"]
    health_coordinator: WhiskerHealthCoordinator = runtime["health"]
    alert_history: AlertHistoryManager | None = runtime.get("alert_history")

    entities: list[SensorEntity] = [
        WhiskerFlaggedVisitsSensor(diag_coordinator, entry),
        WhiskerAiPetIdSensor(diag_coordinator, entry),
        WhiskerHealthSummarySensor(health_coordinator, entry),
    ]
    if alert_history is not None:
        entities.append(WhiskerAlertHistorySensor(alert_history, entry))

    known_pets: set[str] = set()
    pets_map = (health_coordinator.data or {}).get("pets", {})
    for pet_name in pets_map:
        known_pets.add(pet_name)
        entities.append(WhiskerPetHealthSummarySensor(health_coordinator, entry, pet_name))

    async_add_entities(entities)

    @callback
    def _async_discover_new_pets() -> None:
        current_pets = (health_coordinator.data or {}).get("pets", {})
        added: list[SensorEntity] = []
        for pet_name in current_pets:
            if pet_name not in known_pets:
                known_pets.add(pet_name)
                added.append(
                    WhiskerPetHealthSummarySensor(health_coordinator, entry, pet_name)
                )
        if added:
            async_add_entities(added)

    entry.async_on_unload(health_coordinator.async_add_listener(_async_discover_new_pets))


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
        self._attr_device_info = _service_device_info(entry)

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


class WhiskerAiPetIdSensor(
    CoordinatorEntity[WhiskerPetIdCoordinator], SensorEntity
):
    """Status and decision audit sensor for Hybrid + Gemini Vision Auto-Pet-ID."""

    _attr_has_entity_name = True
    _attr_translation_key = "ai_pet_id_status"
    _attr_icon = "mdi:auto-fix"

    def __init__(
        self, coordinator: WhiskerPetIdCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the AI Pet ID status sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ai_pet_id_status"
        self._attr_device_info = _service_device_info(entry)

    @property
    def native_value(self) -> str:
        """Return active Auto-Pet-ID mode (off, dry_run, auto_reassign, or backoff)."""
        payload = self.coordinator.get_ai_status_payload()
        return str(payload.get("state") or "off")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return clean baselines, counters, and last 25 AI Pet ID decisions."""
        payload = dict(self.coordinator.get_ai_status_payload())
        payload.pop("state", None)
        return payload


class WhiskerAlertHistorySensor(SensorEntity):
    """Persistent active & historical alert archive sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "alert_history"
    _attr_icon = "mdi:bell-badge-outline"
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, alert_history: AlertHistoryManager, entry: ConfigEntry
    ) -> None:
        """Initialize the persistent alert history sensor."""
        self._alert_history = alert_history
        self._attr_unique_id = f"{entry.entry_id}_alert_history"
        self._attr_device_info = _service_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe to alert history updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._alert_history.add_listener(self._handle_history_update)
        )

    @callback
    def _handle_history_update(self) -> None:
        """Write updated state when an alert opens or resolves."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return number of currently active alerts in the archive."""
        return int(self._alert_history.get_sensor_payload().get("active_count", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return active alerts, recent 25 alerts, and per-cat/source totals."""
        payload = dict(self._alert_history.get_sensor_payload())
        payload.pop("active_count", None)
        return payload


class WhiskerHealthSummarySensor(
    CoordinatorEntity[WhiskerHealthCoordinator], RestoreEntity, SensorEntity
):
    """Household pet health summary sensor powered by HA AI Task / Gemini."""

    _attr_has_entity_name = True
    _attr_translation_key = "health_summary"
    _attr_icon = "mdi:heart-pulse"

    def __init__(
        self, coordinator: WhiskerHealthCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize household health summary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_health_summary"
        self._attr_device_info = _service_device_info(entry)
        self._restored_state: str | None = None
        self._restored_attrs: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Restore last generated Gemini summary across restarts until replaced."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            self._restored_state = last_state.state
            self._restored_attrs = dict(last_state.attributes)

    def _effective_data(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        if (
            data.get("trigger") == "startup"
            and data.get("generation_mode") == "fallback"
            and self._restored_attrs.get("generation_mode") == "gemini"
        ):
            return {
                **data,
                "overall_status": self._restored_state or data.get("overall_status"),
                "headline": self._restored_attrs.get("headline", data.get("headline")),
                "summary_markdown": self._restored_attrs.get(
                    "summary_markdown", data.get("summary_markdown")
                ),
                "alert_pets": self._restored_attrs.get(
                    "alert_pets", data.get("alert_pets", [])
                ),
                "generation_mode": self._restored_attrs.get("generation_mode"),
                "last_generated_at": self._restored_attrs.get(
                    "last_generated_at", data.get("last_generated_at")
                ),
            }
        return data

    @property
    def native_value(self) -> str:
        """Return overall health status (normal, watch, or alert)."""
        data = self._effective_data()
        return str(data.get("overall_status") or "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full AI health summary attributes for dashboards and automations."""
        data = self._effective_data()
        if not data:
            return {}
        return {
            "robot": data.get("robot"),
            "serial": data.get("serial"),
            "headline": data.get("headline"),
            "summary_markdown": data.get("summary_markdown"),
            "alert_pets": data.get("alert_pets", []),
            "alert_message": data.get("alert_message", ""),
            "generation_mode": data.get("generation_mode"),
            "ai_task_entity": data.get("ai_task_entity"),
            "notify_service": data.get("notify_service"),
            "ai_error": data.get("ai_error"),
            "trigger": data.get("trigger"),
            "last_generated_at": data.get("last_generated_at"),
            "window_hours": data.get("window_hours"),
            "total_visits": data.get("total_visits", 0),
            "unassigned_count": data.get("unassigned_count", 0),
            "flagged_visits_count": data.get("flagged_visits_count", 0),
            "clusters_detected": data.get("clusters_detected", 0),
            "clusters": data.get("clusters", []),
        }


class WhiskerPetHealthSummarySensor(
    CoordinatorEntity[WhiskerHealthCoordinator], RestoreEntity, SensorEntity
):
    """Per-cat health status and trend summary sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "pet_health_summary"
    _attr_icon = "mdi:cat"

    def __init__(
        self,
        coordinator: WhiskerHealthCoordinator,
        entry: ConfigEntry,
        pet_name: str,
    ) -> None:
        """Initialize a per-cat health summary sensor."""
        super().__init__(coordinator)
        self._pet_name = pet_name
        stats = (coordinator.data or {}).get("pets", {}).get(pet_name, {})
        pet_id = stats.get("pet_id") or pet_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{entry.entry_id}_pet_health_{pet_id}"
        self._attr_translation_placeholders = {"pet_name": pet_name}
        self._attr_device_info = _service_device_info(entry)
        self._restored_summary: str | None = None
        self._restored_status: str | None = None
        self._restored_mode: str | None = None

    async def async_added_to_hass(self) -> None:
        """Restore prior Gemini per-cat text across restarts until next generation."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in ("unknown", "unavailable"):
            self._restored_status = last_state.state
            self._restored_summary = last_state.attributes.get("summary")
            self._restored_mode = last_state.attributes.get("generation_mode")

    def _pet_entry(self) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self.coordinator.data or {}
        stats = data.get("pets", {}).get(self._pet_name, {})
        summary_item = data.get("pet_summaries", {}).get(self._pet_name, {})
        if (
            data.get("trigger") == "startup"
            and data.get("generation_mode") == "fallback"
            and self._restored_mode == "gemini"
            and self._restored_summary
        ):
            summary_item = {
                "status": self._restored_status or summary_item.get("status", "normal"),
                "summary": self._restored_summary,
            }
        return stats, summary_item

    @property
    def native_value(self) -> str:
        """Return per-cat health status (normal, watch, or alert)."""
        _, summary_item = self._pet_entry()
        return str(summary_item.get("status") or "unknown")

    @property
    def entity_picture(self) -> str | None:
        """Return cached local Whisker pet avatar thumbnail URL if available."""
        stats, _ = self._pet_entry()
        return stats.get("avatar_url") or self.coordinator.get_pet_avatar(self._pet_name)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-cat metrics, clusters, and summary narrative."""
        data = self.coordinator.data or {}
        stats, summary_item = self._pet_entry()
        return {
            "pet_name": self._pet_name,
            "pet_id": stats.get("pet_id"),
            "summary": summary_item.get("summary"),
            "baseline_weight_lbs": stats.get("baseline_weight_lbs"),
            "avg_weight_lbs": stats.get("avg_weight_lbs"),
            "min_weight_lbs": stats.get("min_weight_lbs"),
            "max_weight_lbs": stats.get("max_weight_lbs"),
            "visits_window": stats.get("visits_window", 0),
            "visits_24h": stats.get("visits_24h", 0),
            "urine_count": stats.get("urine_count", 0),
            "feces_count": stats.get("feces_count", 0),
            "zero_waste_count": stats.get("zero_waste_count", 0),
            "total_waste_grams": stats.get("total_waste_grams", 0.0),
            "avg_duration_seconds": stats.get("avg_duration_seconds"),
            "max_duration_seconds": stats.get("max_duration_seconds"),
            "short_visit_count": stats.get("short_visit_count", 0),
            "long_visit_count": stats.get("long_visit_count", 0),
            "weight_mismatch_count": stats.get("weight_mismatch_count", 0),
            "suspected_redirected_visits": stats.get("suspected_redirected_visits", 0),
            "cluster_detected": stats.get("cluster_detected", False),
            "cluster_max_count": stats.get("cluster_max_count", 0),
            "clusters": stats.get("clusters", []),
            "generation_mode": (
                self._restored_mode
                if (
                    data.get("trigger") == "startup"
                    and data.get("generation_mode") == "fallback"
                    and self._restored_mode == "gemini"
                )
                else data.get("generation_mode")
            ),
            "last_generated_at": data.get("last_generated_at"),
        }
