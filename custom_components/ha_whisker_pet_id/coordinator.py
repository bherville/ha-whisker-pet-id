"""DataUpdateCoordinators for HA Whisker Pet ID diagnostics, auto-verification, and health."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .alert_history import AlertHistoryManager
from .api import (
    async_get_pets_summary,
    async_list_visits,
    async_reassign_visit,
    get_litterrobot_runtime,
    parse_timestamp,
)
from .const import (
    AUTO_ID_STORE_KEY,
    AUTO_ID_STORE_VERSION,
    AUTO_PET_ID_BACKOFF_MINUTES,
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
    DEFAULT_MIN_VALID_WEIGHT_LBS,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_SUMMARY_HOUR,
    DEFAULT_SUMMARY_MINUTE,
    DEFAULT_VIDEO_ESCALATION,
    DOMAIN,
    LITTERROBOT_DOMAIN,
)
from .health import (
    async_generate_ai_health_summary,
    async_send_health_notifications,
    build_fallback_health_summary,
    build_health_context,
)
from .media_source import cleanup_stale_visit_media, get_media_root
from .vision_id import (
    GeminiRateLimitError,
    async_prepare_reference_attachments,
    async_verify_visit_with_gemini,
    compute_clean_baselines,
    evaluate_hybrid_fast_path,
    evaluate_reassignment_safety,
)

_LOGGER = logging.getLogger(__name__)

_MAX_PROCESSED_IDS = 500
_MAX_RECENT_DECISIONS = 25


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
        self._alert_history: AlertHistoryManager | None = None

    def attach_alert_history(self, alert_history: AlertHistoryManager) -> None:
        """Attach persistent alert history manager."""
        self._alert_history = alert_history

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
        report = await self.async_build_report(
            trigger="startup" if not self._bootstrap_done else "refresh",
            use_ai=False,
        )
        if self._alert_history is not None:
            await self._alert_history.async_record_health_report(report)
        return report

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

        if self._alert_history is not None:
            await self._alert_history.async_record_health_report(
                report, notified_services=sent_to
            )

        return {**report, "notified_services": sent_to}


class WhiskerPetIdCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls LR5 PET_VISIT events, runs Hybrid + Gemini Vision Pet ID, and triggers alerts."""

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
        self._alert_history: AlertHistoryManager | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, AUTO_ID_STORE_VERSION, AUTO_ID_STORE_KEY
        )
        self._verify_lock = asyncio.Lock()
        self._reactive_unsub: CALLBACK_TYPE | None = None
        self._debounce_unsub: CALLBACK_TYPE | None = None
        self._processed_ids: list[str] = []
        self._processed_set: set[str] = set()
        self._clean_baselines: dict[str, float] = {}
        self._recent_decisions: list[dict[str, Any]] = []
        self._backoff_until: datetime | None = None
        self._stats: dict[str, Any] = {
            "auto_reassigned_count": 0,
            "scale_unassigned_count": 0,
            "fast_path_count": 0,
            "gemini_calls_count": 0,
            "suggested_count": 0,
            "uncertain_count": 0,
            "last_run_at": None,
            "last_error": None,
        }

    def option(self, key: str, default: Any) -> Any:
        """Read a configured option from the entry with fallback default."""
        return self.config_entry.options.get(key, default)

    def attach_health_coordinator(
        self, health_coordinator: WhiskerHealthCoordinator
    ) -> None:
        """Attach health coordinator for reactive cluster alerts on poll updates."""
        self._health_coordinator = health_coordinator

    def attach_alert_history(self, alert_history: AlertHistoryManager) -> None:
        """Attach persistent alert history manager."""
        self._alert_history = alert_history

    async def async_load_store(self) -> None:
        """Load persisted processed event IDs, baselines, and decision audit log."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            raw_ids = stored.get("processed_event_ids") or []
            if isinstance(raw_ids, list):
                self._processed_ids = [str(eid) for eid in raw_ids[-_MAX_PROCESSED_IDS:]]
                self._processed_set = set(self._processed_ids)

            raw_bases = stored.get("clean_baselines") or {}
            if isinstance(raw_bases, dict):
                self._clean_baselines = {
                    str(k): round(float(v), 2)
                    for k, v in raw_bases.items()
                    if isinstance(v, (int, float)) and float(v) > 0
                }

            raw_decisions = stored.get("recent_decisions") or []
            if isinstance(raw_decisions, list):
                self._recent_decisions = [
                    item for item in raw_decisions[:_MAX_RECENT_DECISIONS] if isinstance(item, dict)
                ]

            raw_stats = stored.get("stats") or {}
            if isinstance(raw_stats, dict):
                for key in self._stats:
                    if key in raw_stats:
                        self._stats[key] = raw_stats[key]

        try:
            root = get_media_root(self.hass)
            await self.hass.async_add_executor_job(cleanup_stale_visit_media, root, 3600)
        except Exception as err:
            _LOGGER.debug("Skipping startup media cache sweep: %s", err)

    async def _async_save_store(self) -> None:
        """Persist processed event IDs, clean baselines, and decision history."""
        await self._store.async_save(
            {
                "processed_event_ids": self._processed_ids[-_MAX_PROCESSED_IDS:],
                "clean_baselines": self._clean_baselines,
                "recent_decisions": self._recent_decisions[:_MAX_RECENT_DECISIONS],
                "stats": self._stats,
            }
        )

    def _record_processed(self, event_id: str) -> None:
        if not event_id or event_id in self._processed_set:
            return
        self._processed_ids.append(event_id)
        self._processed_set.add(event_id)
        if len(self._processed_ids) > _MAX_PROCESSED_IDS:
            removed = self._processed_ids[: len(self._processed_ids) - _MAX_PROCESSED_IDS]
            self._processed_ids = self._processed_ids[-_MAX_PROCESSED_IDS:]
            for old_id in removed:
                self._processed_set.discard(old_id)

    def _record_decision(self, entry: dict[str, Any]) -> None:
        self._recent_decisions.insert(0, entry)
        self._recent_decisions = self._recent_decisions[:_MAX_RECENT_DECISIONS]

    def get_ai_status_payload(self) -> dict[str, Any]:
        """Build attributes snapshot for sensor.ha_whisker_pet_id_ai_pet_id_status."""
        mode = str(self.option(CONF_AUTO_PET_ID_MODE, DEFAULT_AUTO_PET_ID_MODE))
        now_utc = datetime.now(timezone.utc)
        in_backoff = self._backoff_until is not None and now_utc < self._backoff_until
        return {
            "state": "backoff" if in_backoff else mode,
            "mode": mode,
            "enable_hybrid_fast_path": bool(
                self.option(CONF_ENABLE_HYBRID_FAST_PATH, DEFAULT_ENABLE_HYBRID_FAST_PATH)
            ),
            "video_escalation": str(
                self.option(CONF_VIDEO_ESCALATION, DEFAULT_VIDEO_ESCALATION)
            ),
            "auto_pet_id_min_confidence": str(
                self.option(
                    CONF_AUTO_PET_ID_MIN_CONFIDENCE, DEFAULT_AUTO_PET_ID_MIN_CONFIDENCE
                )
            ),
            "auto_unassign_scale_glitches": bool(
                self.option(
                    CONF_AUTO_UNASSIGN_SCALE_GLITCHES,
                    DEFAULT_AUTO_UNASSIGN_SCALE_GLITCHES,
                )
            ),
            "auto_pet_id_notify": str(
                self.option(CONF_AUTO_PET_ID_NOTIFY, DEFAULT_AUTO_PET_ID_NOTIFY)
            ),
            "clean_baselines": dict(self._clean_baselines),
            "auto_reassigned_count": int(self._stats.get("auto_reassigned_count", 0)),
            "scale_unassigned_count": int(self._stats.get("scale_unassigned_count", 0)),
            "fast_path_count": int(self._stats.get("fast_path_count", 0)),
            "gemini_calls_count": int(self._stats.get("gemini_calls_count", 0)),
            "suggested_count": int(self._stats.get("suggested_count", 0)),
            "uncertain_count": int(self._stats.get("uncertain_count", 0)),
            "backoff_until": (
                self._backoff_until.isoformat() if in_backoff and self._backoff_until else None
            ),
            "last_run_at": self._stats.get("last_run_at"),
            "last_error": self._stats.get("last_error"),
            "recent_decisions": list(self._recent_decisions),
        }

    def start_reactive_listener(self) -> None:
        """Watch core litterrobot pet sensors for visits and debounce clip verification."""
        self.stop_reactive_listener()
        if str(self.option(CONF_AUTO_PET_ID_MODE, DEFAULT_AUTO_PET_ID_MODE)) == "off":
            return

        try:
            ent_reg = er.async_get(self.hass)
            watched = [
                entry.entity_id
                for entry in ent_reg.entities.values()
                if entry.platform == LITTERROBOT_DOMAIN
                and entry.domain == "sensor"
                and (
                    entry.entity_id.endswith("_weight")
                    or entry.entity_id.endswith("_pet_visits")
                    or entry.entity_id.endswith("_visits_today")
                )
            ]
        except Exception as err:
            _LOGGER.debug("Unable to enumerate litterrobot entities: %s", err)
            watched = []

        if not watched:
            return

        self._reactive_unsub = async_track_state_change_event(
            self.hass, watched, self._async_on_litterrobot_event
        )
        _LOGGER.debug("Watching %s litterrobot entities for Pet ID verification", len(watched))

    def stop_reactive_listener(self) -> None:
        """Cancel reactive state listeners and any pending debounce timer."""
        if self._reactive_unsub is not None:
            self._reactive_unsub()
            self._reactive_unsub = None
        if self._debounce_unsub is not None:
            self._debounce_unsub()
            self._debounce_unsub = None

    @callback
    def _async_on_litterrobot_event(self, event: Event) -> None:
        """Schedule a debounced verification check after a Litter-Robot visit arrives."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return
        if new_state.state in ("unknown", "unavailable", old_state.state):
            return
        if str(self.option(CONF_AUTO_PET_ID_MODE, DEFAULT_AUTO_PET_ID_MODE)) == "off":
            return

        delay = int(
            self.option(
                CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                DEFAULT_AUTO_PET_ID_CLIP_DELAY_SECONDS,
            )
        )
        if self._debounce_unsub is not None:
            self._debounce_unsub()
        self._debounce_unsub = async_call_later(
            self.hass,
            max(30, delay),
            self._async_reactive_timer_fired,
        )

    @callback
    def _async_reactive_timer_fired(self, _now: datetime) -> None:
        """Launch delayed verification once LR5 camera clip has had time to upload."""
        self._debounce_unsub = None
        self.hass.async_create_task(self._async_run_auto_verify_safe("reactive"))

    async def _async_run_auto_verify_safe(self, trigger: str) -> None:
        try:
            await self.async_verify_visits_with_ai(trigger=trigger)
        except Exception as err:
            _LOGGER.warning("Automatic Pet ID verification (%s) failed: %s", trigger, err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch recent PET_VISIT events and run safety-net auto-verification if needed."""
        try:
            data = await async_list_visits(
                self.hass,
                limit=50,
                activity_type="PET_VISIT",
                include_clips=False,
                baseline_overrides=self._clean_baselines or None,
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

        mode = str(self.option(CONF_AUTO_PET_ID_MODE, DEFAULT_AUTO_PET_ID_MODE))
        now_utc = datetime.now(timezone.utc)
        in_backoff = self._backoff_until is not None and now_utc < self._backoff_until
        if mode != "off" and not in_backoff and not self._verify_lock.locked():
            clip_delay = int(
                self.option(
                    CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                    DEFAULT_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                )
            )
            has_pending = any(
                not v.get("is_reassigned")
                and v.get("event_id") not in self._processed_set
                and (
                    (visit_dt := parse_timestamp(v.get("timestamp"))) is None
                    or (now_utc - visit_dt).total_seconds() >= clip_delay
                )
                for v in flagged
            )
            if has_pending:
                self.hass.async_create_task(self._async_run_auto_verify_safe("poll"))

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
            "auto_pet_id": self.get_ai_status_payload(),
        }

    async def async_verify_visits_with_ai(
        self,
        *,
        trigger: str = "service",
        event_id: str | None = None,
        dry_run: bool | None = None,
        limit: int = 10,
        video_escalation: str | None = None,
        robot_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Evaluate flagged visits via Hybrid Fast-Path and Gemini Vision with safety gates."""
        async with self._verify_lock:
            now_utc = datetime.now(timezone.utc)
            if (
                trigger != "service"
                and self._backoff_until is not None
                and now_utc < self._backoff_until
            ):
                return {
                    "skipped": True,
                    "reason": f"Rate-limit backoff active until {self._backoff_until.isoformat()}",
                    "decisions": [],
                }

            configured_mode = str(
                self.option(CONF_AUTO_PET_ID_MODE, DEFAULT_AUTO_PET_ID_MODE)
            )
            if dry_run is True:
                effective_mode = "dry_run"
            elif dry_run is False:
                effective_mode = "auto_reassign"
            elif configured_mode == "off":
                effective_mode = "dry_run" if trigger == "service" else "off"
            else:
                effective_mode = configured_mode

            if effective_mode == "off":
                return {"skipped": True, "reason": "auto_pet_id_mode is off", "decisions": []}

            use_fast_path = bool(
                self.option(CONF_ENABLE_HYBRID_FAST_PATH, DEFAULT_ENABLE_HYBRID_FAST_PATH)
            )
            esc_mode = (
                video_escalation
                if video_escalation is not None
                else str(self.option(CONF_VIDEO_ESCALATION, DEFAULT_VIDEO_ESCALATION))
            )
            min_conf = str(
                self.option(
                    CONF_AUTO_PET_ID_MIN_CONFIDENCE, DEFAULT_AUTO_PET_ID_MIN_CONFIDENCE
                )
            )
            unassign_glitches = bool(
                self.option(
                    CONF_AUTO_UNASSIGN_SCALE_GLITCHES,
                    DEFAULT_AUTO_UNASSIGN_SCALE_GLITCHES,
                )
            )
            notify_mode = str(
                self.option(CONF_AUTO_PET_ID_NOTIFY, DEFAULT_AUTO_PET_ID_NOTIFY)
            )
            ai_task_entity = str(
                self.option(CONF_AI_TASK_ENTITY, DEFAULT_AI_TASK_ENTITY)
            )
            clip_delay = int(
                self.option(
                    CONF_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                    DEFAULT_AUTO_PET_ID_CLIP_DELAY_SECONDS,
                )
            )
            max_per_run = int(
                self.option(CONF_AUTO_PET_ID_MAX_PER_RUN, DEFAULT_AUTO_PET_ID_MAX_PER_RUN)
            )
            batch_cap = min(max(1, limit), max_per_run) if trigger != "service" else max(1, limit)

            _, lr_coordinator, account = get_litterrobot_runtime(self.hass)
            websession = getattr(getattr(account, "session", None), "websession", None)

            pets_resp = await async_get_pets_summary(self.hass, refresh=False)
            pets = pets_resp.get("pets", [])
            self._clean_baselines = compute_clean_baselines(pets, self._clean_baselines)

            visits_resp = await async_list_visits(
                self.hass,
                robot_id=robot_id,
                limit=max(40, batch_cap * 3),
                activity_type="PET_VISIT",
                include_clips=True,
                baseline_overrides=self._clean_baselines,
            )
            visits = visits_resp.get("visits", [])

            if event_id:
                target_id = event_id.strip()
                candidates = [v for v in visits if v.get("event_id") == target_id]
                if not candidates:
                    raise HomeAssistantError(
                        f"PET_VISIT event_id '{target_id}' was not found in recent visits."
                    )
            else:
                candidates = []
                for visit in visits:
                    eid = str(visit.get("event_id") or "")
                    if not eid or not visit.get("flags"):
                        continue
                    if visit.get("is_reassigned") is True and not force:
                        continue
                    if eid in self._processed_set and not force:
                        continue
                    if trigger != "service":
                        vdt = parse_timestamp(visit.get("timestamp"))
                        if vdt is not None and (now_utc - vdt).total_seconds() < clip_delay:
                            continue
                    candidates.append(visit)
                    if len(candidates) >= batch_cap:
                        break

            ref_attachments: list[dict[str, str]] | None = None
            uses_sheet = False
            ref_pet_order: list[str] = []
            media_root = get_media_root(self.hass)

            decisions: list[dict[str, Any]] = []
            mutated = False
            rate_limited = False

            for visit in candidates:
                eid = str(visit.get("event_id") or "")
                weight_lbs = visit.get("weight_lbs")
                assigned_pets = [str(p) for p in (visit.get("assigned_pets") or []) if p]

                if (
                    isinstance(weight_lbs, (int, float))
                    and not isinstance(weight_lbs, bool)
                    and float(weight_lbs) < DEFAULT_MIN_VALID_WEIGHT_LBS
                    and unassign_glitches
                    and assigned_pets
                ):
                    raw_decision = {
                        "recommended_pet": "UNASSIGN",
                        "confidence": "high",
                        "confidence_score": 0.99,
                        "visual_match": "fast_path",
                        "needs_video": False,
                        "stage": "scale_glitch",
                        "reasoning": f"Invalid {float(weight_lbs):.2f} lb scale glitch; unassigning from {assigned_pets[0]}.",
                    }
                else:
                    fast_decision = evaluate_hybrid_fast_path(
                        visit, self._clean_baselines, enabled=use_fast_path
                    )
                    if fast_decision is not None:
                        raw_decision = fast_decision
                        self._stats["fast_path_count"] = int(
                            self._stats.get("fast_path_count", 0)
                        ) + 1
                    else:
                        if ref_attachments is None:
                            ref_attachments, uses_sheet, ref_pet_order = (
                                await async_prepare_reference_attachments(
                                    self.hass,
                                    websession,
                                    pets,
                                    self._clean_baselines,
                                    media_root,
                                )
                            )
                        try:
                            raw_decision = await async_verify_visit_with_gemini(
                                self.hass,
                                websession,
                                visit,
                                pets,
                                self._clean_baselines,
                                ref_attachments,
                                uses_roster_sheet=uses_sheet,
                                ref_pet_order=ref_pet_order,
                                media_root=media_root,
                                ai_task_entity=ai_task_entity,
                                video_escalation=esc_mode,
                                robot_id=robot_id,
                            )
                            self._stats["gemini_calls_count"] = int(
                                self._stats.get("gemini_calls_count", 0)
                            ) + 1
                        except GeminiRateLimitError as rate_err:
                            self._backoff_until = now_utc + timedelta(
                                minutes=AUTO_PET_ID_BACKOFF_MINUTES
                            )
                            self._stats["last_error"] = str(rate_err)
                            rate_limited = True
                            _LOGGER.warning(
                                "Gemini quota/rate-limit hit; pausing auto Pet ID for %sm: %s",
                                AUTO_PET_ID_BACKOFF_MINUTES,
                                rate_err,
                            )
                            break
                        except Exception as err:
                            _LOGGER.warning(
                                "Gemini Pet ID failed on event %s: %s", eid, err
                            )
                            self._stats["last_error"] = str(err)
                            raw_decision = {
                                "recommended_pet": "UNCERTAIN",
                                "confidence": "low",
                                "confidence_score": 0.0,
                                "visual_match": "unclear",
                                "needs_video": False,
                                "stage": "gemini_error",
                                "reasoning": f"Gemini verification error: {err}",
                            }

                gated = evaluate_reassignment_safety(
                    raw_decision,
                    visit,
                    self._clean_baselines,
                    mode=effective_mode,
                    min_confidence=min_conf,
                )
                action = gated["action"]
                from_pet = gated["from_pet"]
                to_pet = gated["to_pet"]

                if action in ("reassign", "assign", "unassign"):
                    try:
                        await async_reassign_visit(
                            self.hass,
                            event_id=eid,
                            from_pet=from_pet,
                            to_pet=to_pet,
                            robot_id=robot_id,
                            refresh=False,
                        )
                        mutated = True
                        if action == "unassign":
                            self._stats["scale_unassigned_count"] = int(
                                self._stats.get("scale_unassigned_count", 0)
                            ) + 1
                        else:
                            self._stats["auto_reassigned_count"] = int(
                                self._stats.get("auto_reassigned_count", 0)
                            ) + 1
                    except HomeAssistantError as mut_err:
                        action = "needs_review"
                        gated["reason"] = f"Whisker mutation failed: {mut_err}"
                        self._stats["last_error"] = str(mut_err)

                if action.startswith("dry_run_"):
                    self._stats["suggested_count"] = int(
                        self._stats.get("suggested_count", 0)
                    ) + 1
                elif action == "needs_review":
                    self._stats["uncertain_count"] = int(
                        self._stats.get("uncertain_count", 0)
                    ) + 1

                record = {
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "event_id": eid,
                    "local_time": visit.get("local_time"),
                    "weight_lbs": weight_lbs,
                    "from_pet": from_pet,
                    "to_pet": to_pet,
                    "stage": raw_decision.get("stage"),
                    "confidence": raw_decision.get("confidence"),
                    "confidence_score": raw_decision.get("confidence_score"),
                    "visual_match": raw_decision.get("visual_match"),
                    "action": action,
                    "reasoning": gated["reason"],
                }
                decisions.append(record)
                self._record_decision(record)
                if raw_decision.get("stage") != "gemini_error":
                    self._record_processed(eid)

            if not rate_limited and decisions:
                self._stats["last_error"] = None
            self._stats["last_run_at"] = datetime.now(timezone.utc).isoformat()
            await self._async_save_store()

            if mutated and lr_coordinator is not None:
                await lr_coordinator.async_request_refresh()

            # Send notifications according to policy
            notified_to: list[str] = []
            notify_target = str(
                self.option(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
            ).strip()
            if notify_target and decisions and notify_mode != "none":
                review_items = [d for d in decisions if d["action"] == "needs_review"]
                action_items = [
                    d for d in decisions if d["action"] in ("reassign", "assign", "unassign")
                ]
                notify_lines: list[str] = []
                title = "Whisker Pet ID Review Needed"
                if notify_mode == "all_actions" and (action_items or review_items):
                    title = "Whisker Pet ID Auto-Update"
                    for item in (action_items + review_items)[:5]:
                        notify_lines.append(
                            f"- {item['action']}: {item['from_pet'] or 'Unassigned'} -> {item['to_pet'] or 'Unassigned'} "
                            f"({item['weight_lbs']} lb, {item['stage']}): {item['reasoning']}"
                        )
                elif notify_mode == "uncertain_only" and review_items:
                    for item in review_items[:5]:
                        notify_lines.append(
                            f"- Review needed ({item['local_time']}, {item['weight_lbs']} lb, currently {item['from_pet'] or 'Unassigned'}): "
                            f"{item['reasoning']}"
                        )

                if notify_lines:
                    notified_to = await async_send_health_notifications(
                        self.hass,
                        notify_target=notify_target,
                        title=title,
                        message="\n".join(notify_lines)[:1800],
                        tag="whisker_pet_id_verification",
                    )

            if self._alert_history is not None:
                for item in decisions:
                    if item["action"] == "needs_review":
                        await self._alert_history.async_record_pet_id_review(
                            item,
                            notified_services=notified_to if notify_mode != "none" else [],
                        )
                    elif item["action"] in ("reassign", "assign", "unassign"):
                        await self._alert_history.async_resolve_pet_id_review(
                            str(item["event_id"])
                        )

            # Update entity snapshots immediately
            if isinstance(self.data, dict):
                if mutated:
                    # Trigger a clean coordinator poll in background without re-entering verify lock
                    self.hass.async_create_task(self.async_request_refresh())
                else:
                    self.async_set_updated_data(
                        {**self.data, "auto_pet_id": self.get_ai_status_payload()}
                    )

            return {
                "mode": effective_mode,
                "trigger": trigger,
                "checked_candidates": len(candidates),
                "mutated": mutated,
                "rate_limited": rate_limited,
                "clean_baselines": dict(self._clean_baselines),
                "notified_services": notified_to,
                "decisions": decisions,
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
