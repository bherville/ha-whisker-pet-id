"""DataUpdateCoordinators for HA Whisker Pet ID diagnostics and Gemini health summaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import async_get_pets_summary, async_list_visits, parse_timestamp
from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_ALERT_COOLDOWN_HOURS,
    CONF_CLUSTER_MIN_VISITS,
    CONF_CLUSTER_WINDOW_MINUTES,
    CONF_ENABLE_DAILY_SUMMARY,
    CONF_ENABLE_PUSH_ALERTS,
    CONF_HEALTH_WINDOW_HOURS,
    CONF_NOTIFY_SERVICE,
    CONF_SUMMARY_HOUR,
    CONF_SUMMARY_MINUTE,
    DEFAULT_AI_TASK_ENTITY,
    DEFAULT_ALERT_COOLDOWN_HOURS,
    DEFAULT_CLUSTER_MIN_VISITS,
    DEFAULT_CLUSTER_WINDOW_MINUTES,
    DEFAULT_ENABLE_DAILY_SUMMARY,
    DEFAULT_ENABLE_PUSH_ALERTS,
    DEFAULT_HEALTH_WINDOW_HOURS,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_SUMMARY_HOUR,
    DEFAULT_SUMMARY_MINUTE,
    DOMAIN,
)
from .health import (
    async_generate_ai_health_summary,
    async_send_health_notifications,
    build_fallback_health_summary,
    build_health_context,
)

_LOGGER = logging.getLogger(__name__)


class WhiskerHealthCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Generates AI-assisted and fallback pet health summaries + push alerts."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the health summary coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_health",
            update_interval=None,
        )
        self._daily_unsub: CALLBACK_TYPE | None = None
        self._last_alert_by_pet: dict[str, tuple[str, datetime]] = {}
        self._bootstrap_done = False

    def option(self, key: str, default: Any) -> Any:
        """Read a configured option from the entry with fallback default."""
        return self.config_entry.options.get(key, default)

    def start_schedule(self) -> None:
        """Start daily summary schedule listener if enabled in options."""
        self.stop_schedule()
        if not bool(self.option(CONF_ENABLE_DAILY_SUMMARY, DEFAULT_ENABLE_DAILY_SUMMARY)):
            return
        hour = int(self.option(CONF_SUMMARY_HOUR, DEFAULT_SUMMARY_HOUR))
        minute = int(self.option(CONF_SUMMARY_MINUTE, DEFAULT_SUMMARY_MINUTE))
        self._daily_unsub = async_track_time_change(
            self.hass,
            self._async_scheduled_daily,
            hour=hour,
            minute=minute,
            second=0,
        )

    def stop_schedule(self) -> None:
        """Unsubscribe from any active daily schedule listener."""
        if self._daily_unsub is not None:
            self._daily_unsub()
            self._daily_unsub = None

    async def _async_scheduled_daily(self, _now: datetime) -> None:
        """Run the scheduled daily Gemini health summary."""
        try:
            await self.async_run_health_summary(
                trigger="daily_schedule",
                use_ai=True,
                notify=bool(self.option(CONF_ENABLE_PUSH_ALERTS, DEFAULT_ENABLE_PUSH_ALERTS)),
            )
        except Exception as err:
            _LOGGER.warning("Scheduled daily health summary failed: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Bootstrap deterministic health snapshot on initial setup without spending LLM tokens."""
        return await self.async_build_report(
            trigger="startup" if not self._bootstrap_done else "refresh",
            use_ai=False,
        )

    async def async_build_report(
        self,
        *,
        trigger: str,
        use_ai: bool,
        window_hours: int | None = None,
        ai_task_entity: str | None = None,
        robot_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch cleaned Whisker telemetry and generate summary payload."""
        hours = int(
            window_hours
            if window_hours is not None
            else self.option(CONF_HEALTH_WINDOW_HOURS, DEFAULT_HEALTH_WINDOW_HOURS)
        )
        cluster_window = int(
            self.option(CONF_CLUSTER_WINDOW_MINUTES, DEFAULT_CLUSTER_WINDOW_MINUTES)
        )
        cluster_min = int(
            self.option(CONF_CLUSTER_MIN_VISITS, DEFAULT_CLUSTER_MIN_VISITS)
        )
        task_entity = (
            ai_task_entity
            if ai_task_entity is not None
            else str(self.option(CONF_AI_TASK_ENTITY, DEFAULT_AI_TASK_ENTITY))
        )

        try:
            visits_resp = await async_list_visits(
                self.hass,
                robot_id=robot_id,
                limit=200,
                activity_type="PET_VISIT",
                include_clips=False,
            )
            pets_resp = await async_get_pets_summary(self.hass, refresh=False)
        except HomeAssistantError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching health telemetry: {err}") from err

        context = build_health_context(
            visits_resp.get("visits", []),
            pets_resp.get("pets", []),
            tz_name=str(visits_resp.get("timezone") or self.hass.config.time_zone or "UTC"),
            window_hours=hours,
            cluster_window_minutes=cluster_window,
            cluster_min_visits=cluster_min,
        )

        if use_ai:
            summary = await async_generate_ai_health_summary(
                self.hass,
                context,
                ai_task_entity=task_entity,
                use_ai=True,
            )
        else:
            summary = build_fallback_health_summary(context)

        self._bootstrap_done = True
        return {
            "robot": visits_resp.get("robot"),
            "serial": visits_resp.get("serial"),
            "trigger": trigger,
            "ai_task_entity": task_entity,
            "notify_service": str(
                self.option(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
            ),
            "last_generated_at": context["generated_at"],
            "window_hours": context["window_hours"],
            "total_visits": context["total_visits"],
            "unassigned_count": context["unassigned_count"],
            "flagged_visits_count": context["flagged_visits_count"],
            "clusters_detected": context["clusters_detected"],
            "clusters": context["clusters"],
            "pets": context["pets"],
            **summary,
        }

    def should_trigger_cluster_alert(self, cluster: dict[str, Any]) -> bool:
        """Return True if a detected cluster is new or past alert cooldown."""
        pet_name = str(cluster.get("pet_name") or "")
        end_str = str(cluster.get("end") or "")
        if not pet_name or not end_str:
            return False

        now = datetime.now(timezone.utc)
        cooldown = timedelta(
            hours=int(self.option(CONF_ALERT_COOLDOWN_HOURS, DEFAULT_ALERT_COOLDOWN_HOURS))
        )
        previous = self._last_alert_by_pet.get(pet_name)
        if previous is not None:
            prev_end, prev_sent_at = previous
            if prev_end == end_str:
                return False
            end_dt = parse_timestamp(end_str)
            prev_dt = parse_timestamp(prev_end)
            if (
                end_dt is not None
                and prev_dt is not None
                and end_dt <= prev_dt
                and now - prev_sent_at < cooldown
            ):
                return False
            if now - prev_sent_at < cooldown:
                return False
        return True

    def mark_clusters_alerted(self, clusters: list[dict[str, Any]]) -> None:
        """Record latest alerted cluster timestamp per pet for cooldown deduplication."""
        now = datetime.now(timezone.utc)
        for cluster in clusters:
            pet_name = str(cluster.get("pet_name") or "")
            end_str = str(cluster.get("end") or "")
            if pet_name and end_str:
                self._last_alert_by_pet[pet_name] = (end_str, now)

    async def async_run_health_summary(
        self,
        *,
        trigger: str = "service",
        use_ai: bool = True,
        notify: bool = False,
        window_hours: int | None = None,
        ai_task_entity: str | None = None,
        notify_service: str | None = None,
        robot_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate a fresh summary, update coordinator entities, and optionally notify."""
        report = await self.async_build_report(
            trigger=trigger,
            use_ai=use_ai,
            window_hours=window_hours,
            ai_task_entity=ai_task_entity,
            robot_id=robot_id,
        )
        self.async_set_updated_data(report)

        sent_to: list[str] = []
        if notify:
            target = (
                notify_service
                if notify_service is not None
                else str(self.option(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE))
            )
            should_push = (
                trigger == "daily_schedule"
                or trigger == "service"
                or report.get("overall_status") in ("watch", "alert")
                or report.get("clusters_detected", 0) > 0
            )
            if should_push and target.strip():
                title_prefix = {
                    "alert": "Whisker Health Alert",
                    "watch": "Whisker Health Watch",
                }.get(str(report.get("overall_status")), "Whisker Daily Health Summary")
                body = (
                    report.get("alert_message")
                    or report.get("headline")
                    or report.get("summary_markdown")
                    or "Pet health summary updated."
                )
                if trigger == "daily_schedule" and report.get("overall_status") == "normal":
                    body = str(report.get("summary_markdown") or report.get("headline") or body)
                sent_to = await async_send_health_notifications(
                    self.hass,
                    notify_target=target,
                    title=title_prefix,
                    message=body[:1800],
                    tag=(
                        "whisker_pet_health_daily"
                        if trigger == "daily_schedule"
                        else "whisker_pet_health_alert"
                    ),
                )
                if sent_to and report.get("clusters"):
                    self.mark_clusters_alerted(report["clusters"])

        return {**report, "notified_services": sent_to}


class WhiskerPetIdCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls recent LR5 PET_VISIT events lightly for diagnostic flagging and cluster alerts."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        self._health_coordinator: WhiskerHealthCoordinator | None = None

    def attach_health_coordinator(
        self, health_coordinator: WhiskerHealthCoordinator
    ) -> None:
        """Attach health coordinator for reactive cluster alerts on poll updates."""
        self._health_coordinator = health_coordinator

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch recent PET_VISIT events without scanning paginated video clips."""
        try:
            data = await async_list_visits(
                self.hass,
                limit=50,
                activity_type="PET_VISIT",
                include_clips=False,
            )
        except HomeAssistantError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error fetching LR5 visits: {err}") from err

        visits = data.get("visits", [])
        flagged = [v for v in visits if v.get("flags")]

        if self._health_coordinator is not None:
            await self._maybe_handle_cluster_alerts(
                visits,
                tz_name=str(data.get("timezone") or self.hass.config.time_zone or "UTC"),
            )

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

    async def _maybe_handle_cluster_alerts(
        self, visits: list[dict[str, Any]], *, tz_name: str
    ) -> None:
        """Detect newly formed repeat-visit clusters deterministically before invoking Gemini."""
        hc = self._health_coordinator
        if hc is None:
            return
        try:
            pets_resp = await async_get_pets_summary(self.hass, refresh=False)
            ctx = build_health_context(
                visits,
                pets_resp.get("pets", []),
                tz_name=tz_name,
                window_hours=int(
                    hc.option(CONF_HEALTH_WINDOW_HOURS, DEFAULT_HEALTH_WINDOW_HOURS)
                ),
                cluster_window_minutes=int(
                    hc.option(CONF_CLUSTER_WINDOW_MINUTES, DEFAULT_CLUSTER_WINDOW_MINUTES)
                ),
                cluster_min_visits=int(
                    hc.option(CONF_CLUSTER_MIN_VISITS, DEFAULT_CLUSTER_MIN_VISITS)
                ),
            )
            fresh_clusters = [
                c
                for c in ctx.get("clusters", [])
                if hc.should_trigger_cluster_alert(c)
            ]
            if fresh_clusters:
                push_enabled = bool(
                    hc.option(CONF_ENABLE_PUSH_ALERTS, DEFAULT_ENABLE_PUSH_ALERTS)
                )
                report = await hc.async_run_health_summary(
                    trigger="cluster_alert",
                    use_ai=True,
                    notify=push_enabled,
                )
                hc.mark_clusters_alerted(fresh_clusters)
                _LOGGER.info(
                    "Cluster alert processed (%s clusters, status=%s, notified=%s)",
                    len(fresh_clusters),
                    report.get("overall_status"),
                    report.get("notified_services"),
                )
        except Exception as err:
            _LOGGER.debug("Skipping reactive cluster check: %s", err)
