"""DataUpdateCoordinator for HA Whisker Pet ID diagnostic sensor."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import async_list_visits
from .const import DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class WhiskerPetIdCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls recent LR5 PET_VISIT events lightly for diagnostic flagging."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch recent PET_VISIT events without scanning paginated video clips."""
        try:
            data = await async_list_visits(
                self.hass,
                limit=40,
                activity_type="PET_VISIT",
                include_clips=False,
            )
        except HomeAssistantError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching LR5 visits: {err}") from err

        visits = data.get("visits", [])
        flagged = [v for v in visits if v.get("flags")]
        return {
            "robot": data.get("robot"),
            "serial": data.get("serial"),
            "total_visits_checked": len(visits),
            "flagged_count": len(flagged),
            "unassigned_count": sum(
                1 for v in flagged if "unassigned" in v.get("flags", [])
            ),
            "weight_mismatch_count": sum(
                1 for v in flagged if "weight_mismatch" in v.get("flags", [])
            ),
            "scale_anomaly_count": sum(
                1 for v in flagged if "scale_anomaly" in v.get("flags", [])
            ),
            "flagged_visits": [
                {
                    "event_id": v.get("event_id"),
                    "local_time": v.get("local_time"),
                    "weight_lbs": v.get("weight_lbs"),
                    "assigned_pets": v.get("assigned_pets"),
                    "flags": v.get("flags"),
                    "closest_pets": [
                        c.get("name") for c in v.get("closest_pets_by_weight", [])[:2]
                    ],
                }
                for v in flagged[:15]
            ],
        }
