"""Health telemetry aggregation, cluster detection, and Gemini AI Task summaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import parse_timestamp
from .const import (
    DEFAULT_AI_TASK_ENTITY,
    DEFAULT_CLUSTER_MIN_VISITS,
    DEFAULT_CLUSTER_WINDOW_MINUTES,
    DEFAULT_HEALTH_WINDOW_HOURS,
    DEFAULT_LONG_VISIT_SECONDS,
    DEFAULT_SHORT_VISIT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

VALID_STATUSES = ("normal", "watch", "alert")
_STATUS_RANK = {"normal": 0, "watch": 1, "alert": 2}


def _clean_status(value: Any, default: str = "normal") -> str:
    """Normalize a status string into normal|watch|alert."""
    if isinstance(value, str):
        norm = value.strip().casefold()
        if norm in VALID_STATUSES:
            return norm
    return default


def _detect_visit_clusters(
    timestamps: list[tuple[datetime, float | None, str | None]],
    *,
    window_minutes: int,
    min_visits: int,
) -> list[dict[str, Any]]:
    """Detect sliding-window bursts of repeat litter box visits for a single cat."""
    if len(timestamps) < min_visits:
        return []

    ordered = sorted(timestamps, key=lambda item: item[0])
    window = timedelta(minutes=max(1, window_minutes))
    clusters: list[dict[str, Any]] = []

    left = 0
    for right, (right_dt, _, _) in enumerate(ordered):
        while right_dt - ordered[left][0] > window:
            left += 1
        span_count = right - left + 1
        if span_count >= min_visits:
            slice_items = ordered[left : right + 1]
            start_iso = slice_items[0][0].isoformat()
            end_iso = slice_items[-1][0].isoformat()
            zero_waste = sum(
                1 for _, ww, _ in slice_items if ww is None or ww <= 1.0
            )
            entry = {
                "start": start_iso,
                "end": end_iso,
                "count": span_count,
                "zero_waste_count": zero_waste,
                "duration_minutes": round(
                    (slice_items[-1][0] - slice_items[0][0]).total_seconds() / 60.0,
                    1,
                ),
            }
            if clusters and slice_items[0][0] <= parse_timestamp(clusters[-1]["end"]):
                if span_count >= clusters[-1]["count"]:
                    clusters[-1] = entry
            else:
                clusters.append(entry)

    return clusters


def build_health_context(
    visits: list[dict[str, Any]],
    pets: list[dict[str, Any]],
    *,
    tz_name: str = "UTC",
    now: datetime | None = None,
    window_hours: int = DEFAULT_HEALTH_WINDOW_HOURS,
    cluster_window_minutes: int = DEFAULT_CLUSTER_WINDOW_MINUTES,
    cluster_min_visits: int = DEFAULT_CLUSTER_MIN_VISITS,
    baseline_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate normalized LR5 PET_VISIT records into per-pet and household metrics."""
    now_utc = parse_timestamp(now) or datetime.now(timezone.utc)
    cutoff_window = now_utc - timedelta(hours=max(1, window_hours))
    cutoff_24h = now_utc - timedelta(hours=24)

    try:
        tz_info = ZoneInfo(tz_name)
    except Exception:
        tz_info = timezone.utc

    per_pet_visits: dict[str, list[dict[str, Any]]] = {}
    pet_baselines: dict[str, float | None] = {}
    pet_ids: dict[str, str | None] = {}
    ordered_pet_names: list[str] = []

    for pet in pets:
        name = str(pet.get("name") or "").strip()
        if not name:
            continue
        ordered_pet_names.append(name)
        per_pet_visits.setdefault(name, [])
        override_w = (
            baseline_overrides.get(name) if isinstance(baseline_overrides, dict) else None
        )
        if (
            isinstance(override_w, (int, float))
            and not isinstance(override_w, bool)
            and float(override_w) > 0
        ):
            pet_baselines[name] = round(float(override_w), 2)
        else:
            est = pet.get("estimated_weight_lbs")
            pet_baselines[name] = round(float(est), 2) if isinstance(est, (int, float)) else None
        pet_ids[name] = pet.get("pet_id")

    window_visits: list[dict[str, Any]] = []
    unassigned_visits: list[dict[str, Any]] = []
    suspected_redirected_in: dict[str, int] = {name: 0 for name in ordered_pet_names}

    for visit in visits:
        if visit.get("type") not in ("PET_VISIT", "", None):
            continue
        dt = parse_timestamp(visit.get("timestamp") or visit.get("local_time"))
        if dt is None or dt < cutoff_window:
            continue
        window_visits.append(visit)

        assigned = [str(p) for p in (visit.get("assigned_pets") or []) if p]
        flags = list(visit.get("flags") or [])
        closest = visit.get("closest_pets_by_weight") or []

        if not assigned:
            unassigned_visits.append(visit)
            if (
                "scale_anomaly" not in flags
                and closest
                and isinstance(closest[0], dict)
            ):
                cand = closest[0].get("name")
                if cand in suspected_redirected_in:
                    suspected_redirected_in[cand] += 1
            continue

        for name in assigned:
            if name not in per_pet_visits:
                ordered_pet_names.append(name)
                per_pet_visits[name] = []
                pet_baselines.setdefault(name, None)
                pet_ids.setdefault(name, None)
                suspected_redirected_in.setdefault(name, 0)
            per_pet_visits[name].append(visit)

        if "weight_mismatch" in flags and closest and isinstance(closest[0], dict):
            cand = closest[0].get("name")
            if cand and cand not in assigned and cand in suspected_redirected_in:
                suspected_redirected_in[cand] += 1

    per_pet_stats: dict[str, dict[str, Any]] = {}
    all_clusters: list[dict[str, Any]] = []

    for name in ordered_pet_names:
        items = per_pet_visits.get(name, [])
        weights = [
            float(v["weight_lbs"])
            for v in items
            if isinstance(v.get("weight_lbs"), (int, float))
        ]
        durations = [
            int(v["duration_seconds"])
            for v in items
            if isinstance(v.get("duration_seconds"), (int, float))
        ]
        waste_weights = [
            float(v["waste_weight"])
            for v in items
            if isinstance(v.get("waste_weight"), (int, float))
        ]
        visits_24h = 0
        urine_count = 0
        feces_count = 0
        zero_waste_count = 0
        weight_mismatch_count = 0
        cluster_inputs: list[tuple[datetime, float | None, str | None]] = []

        for v in items:
            dt_utc = parse_timestamp(v.get("timestamp") or v.get("local_time"))
            if dt_utc is not None:
                if dt_utc >= cutoff_24h:
                    visits_24h += 1
                ww = v.get("waste_weight")
                cluster_inputs.append(
                    (
                        dt_utc.astimezone(tz_info),
                        float(ww) if isinstance(ww, (int, float)) else None,
                        v.get("waste_type"),
                    )
                )

            wtype = str(v.get("waste_type") or "").casefold()
            if wtype == "urine":
                urine_count += 1
            elif wtype == "feces":
                feces_count += 1

            ww_raw = v.get("waste_weight")
            if ww_raw is None or (isinstance(ww_raw, (int, float)) and float(ww_raw) <= 1.0):
                zero_waste_count += 1

            if "weight_mismatch" in (v.get("flags") or []):
                weight_mismatch_count += 1

        clusters = _detect_visit_clusters(
            cluster_inputs,
            window_minutes=cluster_window_minutes,
            min_visits=cluster_min_visits,
        )
        for cl in clusters:
            all_clusters.append({"pet_name": name, **cl})

        short_count = sum(1 for d in durations if d <= DEFAULT_SHORT_VISIT_SECONDS)
        long_count = sum(1 for d in durations if d >= DEFAULT_LONG_VISIT_SECONDS)

        per_pet_stats[name] = {
            "pet_id": pet_ids.get(name),
            "pet_name": name,
            "baseline_weight_lbs": pet_baselines.get(name),
            "avg_weight_lbs": round(sum(weights) / len(weights), 2) if weights else None,
            "min_weight_lbs": round(min(weights), 2) if weights else None,
            "max_weight_lbs": round(max(weights), 2) if weights else None,
            "visits_window": len(items),
            "visits_24h": visits_24h,
            "urine_count": urine_count,
            "feces_count": feces_count,
            "zero_waste_count": zero_waste_count,
            "total_waste_grams": round(sum(waste_weights), 1),
            "avg_duration_seconds": round(sum(durations) / len(durations), 1)
            if durations
            else None,
            "max_duration_seconds": max(durations) if durations else None,
            "short_visit_count": short_count,
            "long_visit_count": long_count,
            "weight_mismatch_count": weight_mismatch_count,
            "suspected_redirected_visits": suspected_redirected_in.get(name, 0),
            "cluster_detected": bool(clusters),
            "cluster_max_count": max((c["count"] for c in clusters), default=0),
            "clusters": clusters,
        }

    flagged_window = [v for v in window_visits if v.get("flags")]
    notable_events = [
        {
            "local_time": v.get("local_time") or v.get("timestamp"),
            "assigned_pets": v.get("assigned_pets") or [],
            "weight_lbs": v.get("weight_lbs"),
            "duration_seconds": v.get("duration_seconds"),
            "waste_type": v.get("waste_type"),
            "waste_weight": v.get("waste_weight"),
            "flags": v.get("flags") or [],
            "closest_pet": (
                v["closest_pets_by_weight"][0].get("name")
                if v.get("closest_pets_by_weight")
                else None
            ),
        }
        for v in window_visits[:35]
    ]

    return {
        "generated_at": now_utc.isoformat(),
        "timezone": tz_name,
        "window_hours": window_hours,
        "cluster_window_minutes": cluster_window_minutes,
        "cluster_min_visits": cluster_min_visits,
        "total_visits": len(window_visits),
        "unassigned_count": len(unassigned_visits),
        "flagged_visits_count": len(flagged_window),
        "clusters_detected": len(all_clusters),
        "clusters": all_clusters,
        "pets": per_pet_stats,
        "recent_visits_sample": notable_events,
    }


def build_fallback_health_summary(
    context: dict[str, Any],
    *,
    ai_error: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic structured health summary when Gemini is skipped or unavailable."""
    pets_ctx: dict[str, dict[str, Any]] = context.get("pets", {})
    per_pet_out: dict[str, dict[str, Any]] = {}
    watch_pets: list[str] = []
    alert_pets: list[str] = []

    for name, stats in pets_ctx.items():
        reasons: list[str] = []
        status = "normal"

        if stats.get("cluster_detected"):
            status = "alert"
            reasons.append(
                f"{stats['cluster_max_count']} visits within {context['cluster_window_minutes']}m"
            )
        elif stats.get("visits_24h", 0) >= 8:
            status = "watch"
            reasons.append(f"{stats['visits_24h']} visits in last 24h")

        if (stats.get("long_visit_count") or 0) >= 2 and _STATUS_RANK[status] < 1:
            status = "watch"
            reasons.append(f"{stats['long_visit_count']} long visits (>3m)")

        if (stats.get("weight_mismatch_count") or 0) >= 2:
            reasons.append(
                f"{stats['weight_mismatch_count']} visits flagged as Pet ID weight_mismatch"
            )

        if stats.get("visits_window", 0) == 0:
            if _STATUS_RANK[status] < 1:
                status = "watch"
            reasons.append(f"0 recorded visits in last {context['window_hours']}h")

        if status == "alert":
            alert_pets.append(name)
        elif status == "watch":
            watch_pets.append(name)

        wt_str = (
            f"avg {stats['avg_weight_lbs']:.2f} lb (baseline {stats['baseline_weight_lbs']:.2f} lb)"
            if stats.get("avg_weight_lbs") is not None and stats.get("baseline_weight_lbs") is not None
            else (
                f"baseline {stats['baseline_weight_lbs']:.2f} lb"
                if stats.get("baseline_weight_lbs") is not None
                else "no recent weights"
            )
        )
        detail = "; ".join(reasons) if reasons else "Normal cadence and weights."
        per_pet_out[name] = {
            "status": status,
            "summary": (
                f"{stats['visits_24h']} visits/24h ({stats['visits_window']} in {context['window_hours']}h), "
                f"{wt_str}. {detail}"
            ),
        }

    if alert_pets:
        overall = "alert"
    elif watch_pets or (context.get("flagged_visits_count", 0) >= 5):
        overall = "watch"
    else:
        overall = "normal"

    flagged_names = alert_pets + [p for p in watch_pets if p not in alert_pets]
    if alert_pets:
        headline = f"Alert: visit clustering/anomaly flagged for {', '.join(alert_pets)}."
    elif watch_pets:
        headline = f"Watch: review activity/Pet IDs for {', '.join(watch_pets)}."
    elif context.get("flagged_visits_count", 0) > 0:
        headline = f"{context['total_visits']} visits in {context['window_hours']}h ({context['flagged_visits_count']} Pet ID flags)."
    else:
        headline = f"All pets look normal across {context['total_visits']} visits ({context['window_hours']}h)."

    lines = [
        f"### Litter-Robot Health Summary ({context['window_hours']}h)",
        f"**Overall:** `{overall}` — {headline}",
        "",
    ]
    for name, item in per_pet_out.items():
        lines.append(f"- **{name}** (`{item['status']}`): {item['summary']}")
    if context.get("unassigned_count", 0) or context.get("flagged_visits_count", 0):
        lines.append(
            f"\n_Pet ID note: {context['flagged_visits_count']} flagged / {context['unassigned_count']} unassigned visits in window._"
        )
    if ai_error:
        lines.append(f"_Gemini AI Task fallback active: {ai_error}_")
    lines.append("_Informational trend summary only; not a veterinary diagnosis._")

    alert_msg = ""
    if overall in ("watch", "alert"):
        parts = [headline]
        for pname in flagged_names[:3]:
            parts.append(f"{pname}: {per_pet_out[pname]['summary']}")
        alert_msg = "\n".join(parts)

    return {
        "overall_status": overall,
        "headline": headline,
        "summary_markdown": "\n".join(lines),
        "alert_pets": flagged_names,
        "alert_message": alert_msg,
        "pet_summaries": per_pet_out,
        "generation_mode": "fallback",
        "ai_error": ai_error,
    }


def _build_gemini_instructions(context: dict[str, Any]) -> str:
    """Create a concise, context-rich prompt for Home Assistant ai_task.generate_data."""
    compact_context = {
        "window_hours": context["window_hours"],
        "timezone": context["timezone"],
        "cluster_rule": f">={context['cluster_min_visits']} visits within {context['cluster_window_minutes']} minutes",
        "total_visits": context["total_visits"],
        "unassigned_count": context["unassigned_count"],
        "flagged_visits_count": context["flagged_visits_count"],
        "clusters": context["clusters"],
        "pets": {
            name: {
                key: val
                for key, val in stats.items()
                if key != "pet_id"
            }
            for name, stats in context["pets"].items()
        },
        "recent_visits_sample": context["recent_visits_sample"][:25],
    }
    return (
        "You are analyzing multi-cat Litter-Robot 5 Pro telemetry for a veterinary wellness summary.\n"
        "Review the per-cat counts, weights, durations, waste types, repeat-visit clusters, and recent sample below.\n"
        "Important Pet ID caveat: if a visit carries 'weight_mismatch' and 'closest_pet' points to a heavier/different cat "
        "(for example an ~11.5 lb visit misassigned to an ~8.6 lb cat), note that those clustered visits likely belong to "
        "the weight-matched cat and mention that Pet ID reassignment is needed.\n"
        "Set overall_status to 'alert' when urinary clustering/straining or acute behavioral shifts appear, 'watch' for mild "
        "elevations, missing-visit gaps, or frequent Pet ID mismatches, and 'normal' otherwise.\n"
        "In pet_summaries_json, return a valid JSON object mapping EVERY pet name in `pets` to "
        '{"status": "normal|watch|alert", "summary": "short 1-2 sentence assessment"}.\n'
        "In alert_pets, return a comma-separated list of pet names needing watch/alert attention, or 'none'.\n"
        "Include a brief reminder that this is not a veterinary diagnosis.\n\n"
        f"Telemetry JSON:\n{json.dumps(compact_context, separators=(',', ':'))}"
    )


def _parse_gemini_response(
    raw_data: Any,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Normalize structured output returned by ai_task.generate_data."""
    if not isinstance(raw_data, dict):
        raise ValueError("ai_task.generate_data returned non-dict data")

    fallback = build_fallback_health_summary(context)
    overall = _clean_status(raw_data.get("overall_status"), fallback["overall_status"])
    headline = str(raw_data.get("headline") or fallback["headline"]).strip()
    summary_md = str(raw_data.get("summary_markdown") or fallback["summary_markdown"]).strip()

    raw_alert_pets = str(raw_data.get("alert_pets") or "").strip()
    if not raw_alert_pets or raw_alert_pets.casefold() in ("none", "n/a", "[]"):
        alert_pets = []
    else:
        known_lookup = {k.casefold(): k for k in context.get("pets", {})}
        alert_pets = []
        for token in raw_alert_pets.replace(";", ",").split(","):
            clean = token.strip()
            if not clean:
                continue
            alert_pets.append(known_lookup.get(clean.casefold(), clean))

    raw_alert_msg = str(raw_data.get("alert_message") or "").strip()
    alert_msg = "" if raw_alert_msg.casefold() in ("", "none", "n/a") else raw_alert_msg

    pet_summaries: dict[str, dict[str, Any]] = {}
    parsed_json: dict[str, Any] = {}
    raw_pets_field = raw_data.get("pet_summaries_json")
    if isinstance(raw_pets_field, dict):
        parsed_json = raw_pets_field
    elif isinstance(raw_pets_field, str) and raw_pets_field.strip():
        text = raw_pets_field.strip()
        if text.startswith("```"):
            lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            candidate = json.loads(text)
            if isinstance(candidate, dict):
                parsed_json = candidate
        except ValueError:
            parsed_json = {}

    parsed_by_cf = {str(k).casefold(): v for k, v in parsed_json.items()}
    for name, fb_item in fallback["pet_summaries"].items():
        entry = parsed_by_cf.get(name.casefold())
        if isinstance(entry, dict):
            pet_summaries[name] = {
                "status": _clean_status(entry.get("status"), fb_item["status"]),
                "summary": str(entry.get("summary") or fb_item["summary"]).strip(),
            }
        elif isinstance(entry, str) and entry.strip():
            pet_summaries[name] = {
                "status": fb_item["status"],
                "summary": entry.strip(),
            }
        else:
            pet_summaries[name] = fb_item

    return {
        "overall_status": overall,
        "headline": headline,
        "summary_markdown": summary_md,
        "alert_pets": alert_pets,
        "alert_message": alert_msg or (headline if overall in ("watch", "alert") else ""),
        "pet_summaries": pet_summaries,
        "generation_mode": "gemini",
        "ai_error": None,
    }


async def async_generate_ai_health_summary(
    hass: HomeAssistant,
    context: dict[str, Any],
    *,
    ai_task_entity: str = DEFAULT_AI_TASK_ENTITY,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Generate a structured health summary using Home Assistant's ai_task or fallback."""
    target_entity = (ai_task_entity or "").strip()
    if not use_ai or not target_entity:
        return build_fallback_health_summary(context)

    if not hass.services.has_service("ai_task", "generate_data"):
        return build_fallback_health_summary(
            context,
            ai_error="Home Assistant ai_task.generate_data service is not available.",
        )

    structure = {
        "overall_status": {
            "description": "Overall status: normal, watch, or alert",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "headline": {
            "description": "One concise headline sentence (<=120 chars)",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "summary_markdown": {
            "description": "Concise markdown summary covering household and each pet plus any Pet ID caveats",
            "required": True,
            "selector": {"text": {"multiline": True}},
        },
        "alert_pets": {
            "description": "Comma-separated pet names with watch/alert concerns, or 'none'",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "alert_message": {
            "description": "Short mobile push notification message if status is watch/alert, else 'none'",
            "required": True,
            "selector": {"text": {"multiline": True}},
        },
        "pet_summaries_json": {
            "description": 'JSON object mapping each pet name to {"status": "normal|watch|alert", "summary": "..."}',
            "required": True,
            "selector": {"text": {"multiline": True}},
        },
    }

    try:
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": target_entity,
                "task_name": "Whisker Pet Health Summary",
                "instructions": _build_gemini_instructions(context),
                "structure": structure,
            },
            blocking=True,
            return_response=True,
        )
        raw_data = response.get("data") if isinstance(response, dict) else response
        return _parse_gemini_response(raw_data, context)
    except (HomeAssistantError, Exception) as err:
        _LOGGER.warning(
            "Gemini ai_task (%s) failed, using deterministic health fallback: %s",
            target_entity,
            err,
        )
        return build_fallback_health_summary(context, ai_error=str(err))


def parse_notify_targets(notify_target: str | None) -> list[tuple[str, str]]:
    """Parse one or more comma-separated Home Assistant notify services into (domain, service)."""
    if not notify_target or not isinstance(notify_target, str):
        return []
    targets: list[tuple[str, str]] = []
    for raw in notify_target.split(","):
        clean = raw.strip()
        if not clean:
            continue
        if clean.startswith("notify."):
            domain, service = clean.split(".", 1)
        elif "." in clean:
            domain, service = clean.split(".", 1)
        else:
            domain, service = "notify", clean
        if service:
            targets.append((domain, service))
    return targets


async def async_send_health_notifications(
    hass: HomeAssistant,
    *,
    notify_target: str | None,
    title: str,
    message: str,
    tag: str = "whisker_pet_health",
) -> list[str]:
    """Dispatch notifications to configured Home Assistant notify services."""
    sent_to: list[str] = []
    for domain, service in parse_notify_targets(notify_target):
        if not hass.services.has_service(domain, service):
            _LOGGER.warning("Configured notify service %s.%s not found", domain, service)
            continue
        try:
            await hass.services.async_call(
                domain,
                service,
                {
                    "title": title,
                    "message": message,
                    "data": {"tag": tag},
                },
                blocking=True,
            )
            sent_to.append(f"{domain}.{service}")
        except Exception as err:
            _LOGGER.warning("Failed sending notification to %s.%s: %s", domain, service, err)
    return sent_to
