"""Persistent historical alert archive and Home Assistant Logbook event emitter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .api import parse_timestamp
from .const import (
    ALERT_HISTORY_MAX_ENTRIES,
    ALERT_HISTORY_STORE_KEY,
    ALERT_HISTORY_STORE_VERSION,
    EVENT_ALERT,
)

_LOGGER = logging.getLogger(__name__)


class AlertHistoryManager:
    """Persist health clusters, summary alerts, and Pet ID review flags across restarts."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        max_entries: int = ALERT_HISTORY_MAX_ENTRIES,
    ) -> None:
        """Initialize the persistent alert history archive."""
        self.hass = hass
        self._max_entries = max(10, int(max_entries))
        self._store: Store[dict[str, Any]] = Store(
            hass, ALERT_HISTORY_STORE_VERSION, ALERT_HISTORY_STORE_KEY
        )
        self._entries: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a listener invoked whenever alert history changes."""
        self._listeners.append(listener)

        @callback
        def _unsub() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsub

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception as err:
                _LOGGER.debug("Alert history listener error: %s", err)

    async def async_load(self) -> None:
        """Load persisted alerts from Home Assistant storage."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            raw = stored.get("entries") or []
            if isinstance(raw, list):
                valid_entries = [
                    dict(item) for item in raw[: self._max_entries] if isinstance(item, dict)
                ]
                filtered_entries = [
                    item
                    for item in valid_entries
                    if not str(item.get("alert_id") or "").startswith("health_summary:")
                ]
                pruned = len(filtered_entries) != len(valid_entries)
                self._entries = filtered_entries
                if pruned:
                    await self.async_save()

    async def async_save(self) -> None:
        """Persist bounded alert list and notify entity listeners."""
        self._entries.sort(key=lambda item: str(item.get("opened_at") or ""), reverse=True)
        self._entries = self._entries[: self._max_entries]
        await self._store.async_save({"entries": self._entries})
        self._notify_listeners()

    def _fire_alert_event(self, action: str, entry: dict[str, Any]) -> None:
        """Emit a native HA event for Logbook and automations."""
        bus = getattr(self.hass, "bus", None)
        async_fire = getattr(bus, "async_fire", None)
        if callable(async_fire):
            async_fire(
                EVENT_ALERT,
                {
                    "action": action,
                    "alert_id": entry.get("alert_id"),
                    "source": entry.get("source"),
                    "severity": entry.get("severity"),
                    "pets": entry.get("pets", []),
                    "headline": entry.get("headline", ""),
                    "status": entry.get("status"),
                },
            )

    def _find_entry(self, alert_id: str) -> dict[str, Any] | None:
        for item in self._entries:
            if item.get("alert_id") == alert_id:
                return item
        return None

    async def async_record_health_report(
        self,
        report: dict[str, Any],
        *,
        notified_services: list[str] | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Record active clusters/summary status and auto-resolve cleared alerts."""
        now_dt = parse_timestamp(now) or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        notified = list(notified_services or [])

        changed = False
        opened = 0
        resolved = 0

        # 1. Sync repeat-visit clusters
        active_cluster_ids: set[str] = set()
        for cluster in report.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            pet_name = str(cluster.get("pet_name") or "").strip()
            end_str = str(cluster.get("end") or "").strip()
            if not pet_name or not end_str:
                continue
            alert_id = f"cluster:{pet_name}:{end_str}"
            active_cluster_ids.add(alert_id)

            count = int(cluster.get("count") or 0)
            dur = cluster.get("duration_minutes")
            if isinstance(dur, (int, float)) and not isinstance(dur, bool):
                dur_str = str(round(float(dur)))
            else:
                dur_str = str(dur if dur is not None else 0)
            zw = int(cluster.get("zero_waste_count") or 0)
            if zw > 0:
                headline = f"{count} quick visits in {dur_str} min ({zw} with no waste)"
            else:
                headline = f"{count} quick visits in {dur_str} min"

            existing = self._find_entry(alert_id)
            if existing is None:
                entry = {
                    "alert_id": alert_id,
                    "source": "health_cluster",
                    "severity": "alert",
                    "status": "active",
                    "opened_at": end_str,
                    "last_seen_at": now_iso,
                    "resolved_at": None,
                    "pets": [pet_name],
                    "headline": headline,
                    "notified_services": list(notified),
                    "details": dict(cluster),
                }
                self._entries.insert(0, entry)
                self._fire_alert_event("opened", entry)
                changed = True
                opened += 1
            else:
                if existing.get("status") != "active":
                    existing["status"] = "active"
                    existing["resolved_at"] = None
                    changed = True
                if notified:
                    merged = list(
                        dict.fromkeys([*(existing.get("notified_services") or []), *notified])
                    )
                    if merged != (existing.get("notified_services") or []):
                        existing["notified_services"] = merged
                        changed = True
                if existing.get("last_seen_at") != now_iso:
                    existing["last_seen_at"] = now_iso
                existing["headline"] = headline
                existing["details"] = dict(cluster)

        for item in self._entries:
            if (
                item.get("source") == "health_cluster"
                and item.get("status") == "active"
                and item.get("alert_id") not in active_cluster_ids
            ):
                item["status"] = "resolved"
                item["resolved_at"] = now_iso
                self._fire_alert_event("resolved", item)
                changed = True
                resolved += 1

        # 2. Remove legacy combined household entries & sync one health_summary alert per cat
        before_prune = len(self._entries)
        self._entries = [
            item
            for item in self._entries
            if not str(item.get("alert_id") or "").startswith("health_summary:")
        ]
        if len(self._entries) != before_prune:
            changed = True

        is_startup_fallback = (
            report.get("trigger") == "startup"
            and report.get("generation_mode") == "fallback"
        )
        if not is_startup_fallback:
            overall = str(report.get("overall_status") or "normal").strip().casefold()
            pet_summaries = report.get("pet_summaries") or {}
            flagged_pets_map: dict[str, tuple[str, str]] = {}

            if isinstance(pet_summaries, dict):
                for name, info in pet_summaries.items():
                    if not isinstance(info, dict):
                        continue
                    pet_status = str(info.get("status") or "").strip().casefold()
                    if pet_status not in ("watch", "alert"):
                        continue
                    pet_name = str(name).strip()
                    if not pet_name:
                        continue
                    pet_headline = str(
                        info.get("summary") or f"{pet_name} flagged ({pet_status})"
                    ).strip()
                    flagged_pets_map[pet_name] = (pet_status, pet_headline)

            if not flagged_pets_map and overall in ("watch", "alert"):
                fallback_pets = [str(p).strip() for p in (report.get("alert_pets") or []) if p]
                if not fallback_pets:
                    fallback_pets = ["Household"]
                fallback_msg = str(
                    report.get("headline") or f"Health status: {overall}"
                ).strip()
                for pet_name in fallback_pets:
                    flagged_pets_map[pet_name] = (overall, fallback_msg)

            active_pet_health_ids: set[str] = set()
            for pet_name, (pet_status, pet_headline) in flagged_pets_map.items():
                alert_id = f"pet_health:{pet_name}"
                active_pet_health_ids.add(alert_id)
                details = {
                    "generation_mode": report.get("generation_mode"),
                    "clusters_detected": report.get("clusters_detected", 0),
                    "flagged_visits_count": report.get("flagged_visits_count", 0),
                    "pet_status": pet_status,
                    "household_headline": report.get("headline"),
                }
                existing = self._find_entry(alert_id)
                if existing is None:
                    entry = {
                        "alert_id": alert_id,
                        "source": "health_summary",
                        "severity": pet_status,
                        "status": "active",
                        "opened_at": now_iso,
                        "last_seen_at": now_iso,
                        "resolved_at": None,
                        "pets": [pet_name],
                        "headline": pet_headline,
                        "notified_services": list(notified),
                        "details": details,
                    }
                    self._entries.insert(0, entry)
                    self._fire_alert_event("opened", entry)
                    changed = True
                    opened += 1
                else:
                    if existing.get("status") != "active":
                        existing["status"] = "active"
                        existing["resolved_at"] = None
                        self._fire_alert_event("opened", existing)
                        changed = True
                        opened += 1
                    if existing.get("severity") != pet_status:
                        existing["severity"] = pet_status
                        changed = True
                    if existing.get("headline") != pet_headline:
                        existing["headline"] = pet_headline
                        changed = True
                    if existing.get("pets") != [pet_name]:
                        existing["pets"] = [pet_name]
                        changed = True
                    if notified:
                        merged = list(
                            dict.fromkeys(
                                [*(existing.get("notified_services") or []), *notified]
                            )
                        )
                        if merged != (existing.get("notified_services") or []):
                            existing["notified_services"] = merged
                            changed = True
                    existing["last_seen_at"] = now_iso
                    existing["details"] = details

            for item in self._entries:
                if (
                    item.get("source") == "health_summary"
                    and item.get("status") == "active"
                    and item.get("alert_id") not in active_pet_health_ids
                ):
                    item["status"] = "resolved"
                    item["resolved_at"] = now_iso
                    self._fire_alert_event("resolved", item)
                    changed = True
                    resolved += 1

        if changed:
            await self.async_save()

        return {"opened": opened, "resolved": resolved}

    async def async_record_pet_id_review(
        self,
        decision: dict[str, Any],
        *,
        notified_services: list[str] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Record an ambiguous Pet ID visit requiring human review."""
        event_id = str(decision.get("event_id") or "").strip()
        if not event_id:
            return None

        now_dt = parse_timestamp(now) or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        alert_id = f"pet_id_review:{event_id}"
        pets = [
            str(p)
            for p in dict.fromkeys(
                [decision.get("from_pet"), decision.get("to_pet")]
            )
            if p
        ]
        weight = decision.get("weight_lbs")
        weight_str = f"{weight} lb" if weight is not None else "unknown weight"
        headline = (
            f"Pet ID review ({weight_str}, {decision.get('from_pet') or 'Unassigned'}): "
            f"{decision.get('reasoning') or 'Uncertain identification'}"
        )
        notified = list(notified_services or [])

        existing = self._find_entry(alert_id)
        if existing is None:
            entry = {
                "alert_id": alert_id,
                "source": "pet_id_review",
                "severity": "watch",
                "status": "active",
                "opened_at": str(decision.get("processed_at") or now_iso),
                "last_seen_at": now_iso,
                "resolved_at": None,
                "pets": pets,
                "headline": headline,
                "notified_services": notified,
                "details": {
                    "event_id": event_id,
                    "local_time": decision.get("local_time"),
                    "weight_lbs": weight,
                    "from_pet": decision.get("from_pet"),
                    "to_pet": decision.get("to_pet"),
                    "stage": decision.get("stage"),
                    "confidence": decision.get("confidence"),
                    "confidence_score": decision.get("confidence_score"),
                    "visual_match": decision.get("visual_match"),
                    "reasoning": decision.get("reasoning"),
                },
            }
            self._entries.insert(0, entry)
            self._fire_alert_event("opened", entry)
            await self.async_save()
            return entry

        changed = False
        if existing.get("status") != "active":
            existing["status"] = "active"
            existing["resolved_at"] = None
            self._fire_alert_event("opened", existing)
            changed = True
        if notified:
            merged = list(
                dict.fromkeys([*(existing.get("notified_services") or []), *notified])
            )
            if merged != (existing.get("notified_services") or []):
                existing["notified_services"] = merged
                changed = True
        existing["last_seen_at"] = now_iso
        existing["headline"] = headline
        if changed:
            await self.async_save()
        return existing

    async def async_resolve_pet_id_review(
        self,
        event_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Resolve an active Pet ID review alert once the visit has been reassigned."""
        clean_id = (event_id or "").strip()
        if not clean_id:
            return False
        existing = self._find_entry(f"pet_id_review:{clean_id}")
        if existing is None or existing.get("status") == "resolved":
            return False
        now_dt = parse_timestamp(now) or datetime.now(timezone.utc)
        existing["status"] = "resolved"
        existing["resolved_at"] = now_dt.isoformat()
        self._fire_alert_event("resolved", existing)
        await self.async_save()
        return True

    def query(
        self,
        *,
        pet: str | None = None,
        days: int | None = None,
        severity: str | None = None,
        source: str | None = None,
        active_only: bool = False,
        limit: int = 50,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Filter stored alert history for services and dashboards."""
        now_dt = parse_timestamp(now) or datetime.now(timezone.utc)
        cutoff = (
            now_dt - timedelta(days=days)
            if isinstance(days, int) and days > 0
            else None
        )
        pet_cf = pet.strip().casefold() if isinstance(pet, str) and pet.strip() else None
        sev_cf = (
            severity.strip().casefold()
            if isinstance(severity, str) and severity.strip()
            else None
        )
        src_cf = (
            source.strip().casefold()
            if isinstance(source, str) and source.strip()
            else None
        )

        counts_by_pet: dict[str, int] = {}
        counts_by_source: dict[str, int] = {}
        active_total = 0
        resolved_total = 0
        filtered: list[dict[str, Any]] = []

        for item in self._entries:
            if item.get("status") == "active":
                active_total += 1
            else:
                resolved_total += 1

            src = str(item.get("source") or "unknown")
            counts_by_source[src] = counts_by_source.get(src, 0) + 1
            for pname in item.get("pets") or []:
                counts_by_pet[pname] = counts_by_pet.get(pname, 0) + 1

            if active_only and item.get("status") != "active":
                continue
            if sev_cf and str(item.get("severity") or "").casefold() != sev_cf:
                continue
            if src_cf and src.casefold() != src_cf:
                continue
            if pet_cf and not any(str(p).casefold() == pet_cf for p in (item.get("pets") or [])):
                continue
            if cutoff is not None:
                opened_dt = parse_timestamp(item.get("opened_at"))
                if opened_dt is not None and opened_dt < cutoff:
                    continue
            filtered.append(dict(item))

        return {
            "total_logged": len(self._entries),
            "active_count": active_total,
            "resolved_count": resolved_total,
            "returned_count": min(len(filtered), max(1, limit)),
            "counts_by_pet": counts_by_pet,
            "counts_by_source": counts_by_source,
            "alerts": filtered[: max(1, limit)],
        }

    def get_sensor_payload(self) -> dict[str, Any]:
        """Build state + attributes payload for sensor.ha_whisker_pet_id_alert_history."""
        summary = self.query(limit=25)
        active_alerts = [
            dict(item) for item in self._entries if item.get("status") == "active"
        ][:15]
        return {
            "active_count": summary["active_count"],
            "total_logged": summary["total_logged"],
            "resolved_count": summary["resolved_count"],
            "counts_by_pet": summary["counts_by_pet"],
            "counts_by_source": summary["counts_by_source"],
            "last_alert_at": self._entries[0].get("opened_at") if self._entries else None,
            "active_alerts": active_alerts,
            "recent_alerts": summary["alerts"],
        }
