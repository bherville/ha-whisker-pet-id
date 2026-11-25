"""Whisker Litter-Robot 5 / 5 Pro API helpers for HA Whisker Pet ID."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponseError
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CAMERA_INVENTORY_API,
    DEFAULT_MAX_VALID_WEIGHT_LBS,
    DEFAULT_MIN_VALID_WEIGHT_LBS,
    DEFAULT_WEIGHT_MISMATCH_LBS,
    LITTERROBOT_DOMAIN,
    LR5_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

_FALLBACK_V2_KEY = "cDduZE1vajYxbnBSWlA1Q1Z6OXY0VWowYkc3Njl4eTY3NThRUkJQYg=="


def _decode_v2_api_key() -> str:
    """Decode Whisker's camera API v2 key without hard-failing on import."""
    try:
        from pylitterbot.const import API_V2_ENDPOINT_KEY
        from pylitterbot.utils import decode

        return decode(API_V2_ENDPOINT_KEY)
    except Exception:
        return base64.b64decode(_FALLBACK_V2_KEY).decode("utf-8")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 string or numeric Unix timestamp into a UTC-aware datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except ValueError:
                return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def normalize_weight_lbs(raw_weight: Any) -> float | None:
    """Convert LR5 activity petWeight (pounds * 100 or pounds) to pounds."""
    if raw_weight is None or isinstance(raw_weight, bool):
        return None
    try:
        val = float(raw_weight)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    if val > 40:
        return round(val / 100.0, 2)
    return round(val, 2)


def get_litterrobot_runtime(hass: HomeAssistant) -> tuple[ConfigEntry, Any, Any]:
    """Return (config_entry, coordinator, account) from the loaded litterrobot integration."""
    entries = hass.config_entries.async_entries(LITTERROBOT_DOMAIN)
    for entry in entries:
        if entry.state is ConfigEntryState.LOADED and getattr(entry, "runtime_data", None) is not None:
            coordinator = entry.runtime_data
            account = getattr(coordinator, "account", None)
            if account is not None:
                return entry, coordinator, account
    raise HomeAssistantError(
        "No loaded Whisker (litterrobot) integration found. Ensure Whisker is configured and loaded."
    )


def get_lr5_robots(account: Any) -> list[Any]:
    """Return all Litter-Robot 5 / 5 Pro instances on the account."""
    robots = getattr(account, "robots", None) or []
    return [
        robot
        for robot in robots
        if hasattr(robot, "get_activities") and hasattr(robot, "reassign_pet_visit")
    ]


def resolve_lr5_robot(account: Any, robot_identifier: str | None = None) -> Any:
    """Resolve an LR5 robot by name or serial, or return the sole LR5 robot."""
    lr5_robots = get_lr5_robots(account)
    if not lr5_robots:
        raise HomeAssistantError(
            "No Litter-Robot 5 / 5 Pro found on your Whisker account."
        )
    if not robot_identifier:
        if len(lr5_robots) == 1:
            return lr5_robots[0]
        available = ", ".join(f"{r.name} ({r.serial})" for r in lr5_robots)
        raise HomeAssistantError(
            f"Multiple Litter-Robot 5 units found ({available}); specify 'robot'."
        )

    needle = robot_identifier.strip().casefold()
    for robot in lr5_robots:
        if (
            str(getattr(robot, "serial", "")).casefold() == needle
            or str(getattr(robot, "name", "")).casefold() == needle
        ):
            return robot

    available = ", ".join(f"{r.name} ({r.serial})" for r in lr5_robots)
    raise HomeAssistantError(
        f"No Litter-Robot 5 matching '{robot_identifier}'. Available: {available}"
    )


def resolve_pet_id(account: Any, identifier: str) -> str:
    """Resolve a Whisker pet name (case-insensitive) or petId to its petId."""
    pets = getattr(account, "pets", None) or []
    needle_raw = identifier.strip()
    needle_cf = needle_raw.casefold()
    for pet in pets:
        pet_id = str(getattr(pet, "id", "") or "")
        pet_name = str(getattr(pet, "name", "") or "")
        if pet_id == needle_raw or (pet_name and pet_name.casefold() == needle_cf):
            return pet_id

    available = ", ".join(
        f"{getattr(p, 'name', '?')} ({getattr(p, 'id', '?')})" for p in pets
    )
    raise HomeAssistantError(
        f"No Whisker pet matching '{identifier}'. Available: {available}"
    )


def serialize_pet(pet: Any) -> dict[str, Any]:
    """Serialize a pylitterbot Pet object into JSON-safe dict."""
    raw = pet.to_dict() if hasattr(pet, "to_dict") else {}
    gender = getattr(pet, "gender", None)
    history = []
    for item in (getattr(pet, "weight_history", None) or [])[-15:]:
        ts = getattr(item, "timestamp", None)
        history.append(
            {
                "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "weight_lbs": getattr(item, "weight", None),
            }
        )
    return {
        "pet_id": getattr(pet, "id", None),
        "name": getattr(pet, "name", None),
        "estimated_weight_lbs": getattr(pet, "estimated_weight", None),
        "last_weight_reading_lbs": getattr(pet, "last_weight_reading", None),
        "effective_weight_lbs": getattr(pet, "weight", None),
        "breeds": getattr(pet, "breeds", None),
        "gender": str(gender) if gender is not None else None,
        "pet_tag_id": getattr(pet, "pet_tag_id", None),
        "weight_id_feature_enabled": getattr(pet, "weight_id_feature_enabled", None),
        "image_url": getattr(pet, "image_url", None),
        "is_active": getattr(pet, "is_active", None),
        "weight_history_error_type": raw.get("weightHistoryErrorType"),
        "recent_weight_history": history,
    }


def analyze_visit(
    activity: dict[str, Any],
    pets_by_id: dict[str, Any],
    all_pets: list[Any],
    clips: list[dict[str, Any]],
    tz_name: str,
    *,
    max_clip_delta_seconds: int = 180,
    mismatch_threshold_lbs: float = DEFAULT_WEIGHT_MISMATCH_LBS,
    max_valid_weight_lbs: float = DEFAULT_MAX_VALID_WEIGHT_LBS,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
) -> dict[str, Any]:
    """Normalize a single LR5 activity record, match clips, and flag Pet ID issues."""
    event_id = str(
        activity.get("eventId")
        or activity.get("id")
        or activity.get("messageId")
        or ""
    )
    act_type = str(activity.get("type") or "")
    visit_dt = parse_timestamp(activity.get("timestamp"))
    local_ts: str | None = None
    if visit_dt is not None:
        try:
            local_ts = visit_dt.astimezone(ZoneInfo(tz_name)).isoformat()
        except Exception:
            local_ts = visit_dt.isoformat()

    weight_lbs = normalize_weight_lbs(activity.get("petWeight"))
    assigned_pet_ids = [str(pid) for pid in (activity.get("petIds") or []) if pid]
    assigned_pets = [
        getattr(pets_by_id[pid], "name", pid) if pid in pets_by_id else pid
        for pid in assigned_pet_ids
    ]
    camera_event_ids = [
        str(cid) for cid in (activity.get("cameraEventIds") or []) if cid
    ]

    closest_pets: list[dict[str, Any]] = []
    if weight_lbs is not None:
        candidates = []
        for pet in all_pets:
            est = getattr(pet, "estimated_weight", None)
            if isinstance(est, (int, float)) and est > 0:
                delta = round(weight_lbs - float(est), 2)
                candidates.append(
                    {
                        "pet_id": getattr(pet, "id", None),
                        "name": getattr(pet, "name", None),
                        "baseline_lbs": round(float(est), 2),
                        "delta_lbs": delta,
                        "abs_delta_lbs": round(abs(delta), 2),
                    }
                )
        candidates.sort(key=lambda item: item["abs_delta_lbs"])
        closest_pets = candidates

    flags: list[str] = []
    if act_type == "PET_VISIT" and not assigned_pet_ids:
        flags.append("unassigned")
    if weight_lbs is not None and (
        weight_lbs >= max_valid_weight_lbs or weight_lbs < min_valid_weight_lbs
    ):
        flags.append("scale_anomaly")
    if weight_lbs is not None and assigned_pet_ids:
        assigned_baselines = [
            float(pets_by_id[pid].estimated_weight)
            for pid in assigned_pet_ids
            if pid in pets_by_id
            and isinstance(getattr(pets_by_id[pid], "estimated_weight", None), (int, float))
        ]
        if assigned_baselines and min(
            abs(weight_lbs - baseline) for baseline in assigned_baselines
        ) > mismatch_threshold_lbs:
            flags.append("weight_mismatch")

    matched_clips: list[dict[str, Any]] = []
    cam_id_set = set(camera_event_ids)
    for clip in clips:
        clip_id = str(clip.get("id", ""))
        clip_dt = parse_timestamp(clip.get("createdAt"))
        delta_sec: float | None = None
        if visit_dt is not None and clip_dt is not None:
            delta_sec = round(abs((clip_dt - visit_dt).total_seconds()), 1)

        id_match = bool(clip_id and clip_id in cam_id_set)
        time_match = delta_sec is not None and delta_sec <= max_clip_delta_seconds
        if id_match or time_match:
            matched_clips.append(
                {
                    "clip_id": clip_id,
                    "event_type": clip.get("eventType"),
                    "created_at": clip_dt.isoformat() if clip_dt else None,
                    "duration": clip.get("hlsDuration"),
                    "thumbnail_url": clip.get("videoThumbnail"),
                    "pet_detections": clip.get("petDetections") or [],
                    "time_delta_seconds": delta_sec,
                    "matched_by": "id" if id_match else "timestamp",
                }
            )
    matched_clips.sort(
        key=lambda item: (
            0 if item["matched_by"] == "id" else 1,
            item["time_delta_seconds"] if item["time_delta_seconds"] is not None else 9999,
        )
    )

    return {
        "event_id": event_id,
        "message_id": activity.get("messageId"),
        "type": act_type,
        "timestamp": visit_dt.isoformat() if visit_dt else activity.get("timestamp"),
        "local_time": local_ts,
        "weight_lbs": weight_lbs,
        "waste_type": activity.get("wasteType"),
        "waste_weight": activity.get("wasteWeight"),
        "duration_seconds": activity.get("duration"),
        "assigned_pet_ids": assigned_pet_ids,
        "assigned_pets": assigned_pets,
        "is_reassigned": activity.get("isReassigned"),
        "camera_event_ids": camera_event_ids,
        "flags": flags,
        "closest_pets_by_weight": closest_pets[:3],
        "matched_clips": matched_clips,
        "raw": activity,
    }


async def async_fetch_camera_videos(
    account: Any,
    robot: Any,
    timezone_str: str,
    *,
    date_str: str | None = None,
    limit: int = 60,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Fetch LR5 Pro camera clips with explicit page & timezone params.

    Home Assistant 2026.11.3 bundles pylitterbot==2025.8.0 whose get_camera_videos()
    omits page and timezone, missing the newest clips. Calling the REST inventory
    endpoint directly mirrors the pylitterbot 2025.9.0 fix.
    """
    cam = getattr(robot, "camera_metadata", None)
    device_id = cam.get("deviceId") if isinstance(cam, dict) else None
    if not device_id:
        return []

    url = f"{CAMERA_INVENTORY_API}/prod/v1/cameras/{device_id}/videos"
    if date_str:
        url = f"{url}/{date_str.strip()}"

    headers = {"x-api-key": _decode_v2_api_key()}
    clips: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        try:
            data = await account.session.get(
                url,
                headers=headers,
                params={"page": str(page), "timezone": timezone_str},
            )
        except Exception as err:
            _LOGGER.debug(
                "Failed fetching LR5 camera videos page %s for %s: %s",
                page,
                device_id,
                err,
            )
            break

        if not isinstance(data, list) or not data:
            break

        added = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            clip_id = str(item.get("id", ""))
            if clip_id and clip_id in seen:
                continue
            if clip_id:
                seen.add(clip_id)
            clips.append(item)
            added += 1

        if added == 0 or len(clips) >= limit:
            break

    return clips[:limit]


async def async_get_pets_summary(
    hass: HomeAssistant, *, refresh: bool = False
) -> dict[str, Any]:
    """Return serialized Whisker pet profiles from the loaded litterrobot account."""
    _, _, account = get_litterrobot_runtime(hass)
    if refresh:
        await account.load_pets()
        for pet in getattr(account, "pets", None) or []:
            if hasattr(pet, "fetch_weight_history"):
                await pet.fetch_weight_history()
    pets = [serialize_pet(pet) for pet in (getattr(account, "pets", None) or [])]
    return {"pets": pets, "count": len(pets)}


async def async_list_visits(
    hass: HomeAssistant,
    *,
    robot_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    activity_type: str | None = "PET_VISIT",
    date_str: str | None = None,
    include_clips: bool = True,
    max_clip_delta_seconds: int = 180,
) -> dict[str, Any]:
    """Fetch LR5 activities, join matching camera clips, and flag Pet ID issues."""
    _, _, account = get_litterrobot_runtime(hass)
    robot = resolve_lr5_robot(account, robot_id)

    tz_name = str(hass.config.time_zone or getattr(robot, "timezone", None) or "UTC")
    type_filter = activity_type.strip() if isinstance(activity_type, str) and activity_type.strip() else None

    activities = await robot.get_activities(
        limit=limit,
        offset=offset if offset > 0 else None,
        activity_type=type_filter,
    )

    clips: list[dict[str, Any]] = []
    if include_clips and getattr(robot, "has_camera", False):
        clips = await async_fetch_camera_videos(
            account,
            robot,
            tz_name,
            date_str=date_str,
            limit=max(limit * 2, 60),
        )

    all_pets = list(getattr(account, "pets", None) or [])
    pets_by_id = {
        str(getattr(pet, "id", "")): pet
        for pet in all_pets
        if getattr(pet, "id", None)
    }

    visits = [
        analyze_visit(
            act,
            pets_by_id,
            all_pets,
            clips,
            tz_name,
            max_clip_delta_seconds=max_clip_delta_seconds,
        )
        for act in activities
        if isinstance(act, dict)
    ]

    if date_str:
        prefix = date_str.strip()
        visits = [
            v
            for v in visits
            if (v.get("local_time") or v.get("timestamp") or "").startswith(prefix)
        ]

    flagged_count = sum(1 for v in visits if v["flags"])
    return {
        "robot": getattr(robot, "name", None),
        "serial": getattr(robot, "serial", None),
        "timezone": tz_name,
        "activity_type": type_filter or "ALL",
        "total_returned": len(visits),
        "flagged_count": flagged_count,
        "clips_scanned": len(clips),
        "visits": visits,
    }


async def async_get_clip_urls(
    hass: HomeAssistant, *, clip_id: str, robot_id: str | None = None
) -> dict[str, Any]:
    """Exchange a recorded clip_id for presigned S3 MP4 chunk URLs and HLS cookies."""
    clean_clip_id = clip_id.strip()
    if not clean_clip_id:
        raise HomeAssistantError("clip_id must be a non-empty string.")

    _, _, account = get_litterrobot_runtime(hass)
    resolve_lr5_robot(account, robot_id)

    url = f"{CAMERA_INVENTORY_API}/prod/v1/camera-videos/{quote(clean_clip_id, safe='')}"
    headers: dict[str, str] = {"x-api-key": _decode_v2_api_key()}
    if (auth := await account.session.get_bearer_authorization()) is not None:
        headers["authorization"] = auth

    try:
        async with account.session.websession.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
            cookies = {
                name: morsel.value
                for name, morsel in resp.cookies.items()
                if name.startswith("CloudFront-")
            }
    except (ClientResponseError, ClientError) as err:
        raise HomeAssistantError(
            f"Failed to retrieve playback URLs for clip '{clean_clip_id}': {err}"
        ) from err

    if not isinstance(data, dict):
        raise HomeAssistantError(
            f"Unexpected playback response for clip '{clean_clip_id}'."
        )

    chunks = [
        {
            "id": str(chunk.get("id", "")),
            "download_url": chunk.get("downloadUrl"),
        }
        for chunk in (data.get("chunks") or [])
        if isinstance(chunk, dict) and chunk.get("downloadUrl")
    ]
    return {
        "clip_id": clean_clip_id,
        "hls_url": data.get("hlsUrl"),
        "chunks": chunks,
        "cookies": cookies,
        "raw": data,
    }


async def async_reassign_visit(
    hass: HomeAssistant,
    *,
    event_id: str,
    from_pet: str | None = None,
    to_pet: str | None = None,
    robot_id: str | None = None,
    refresh: bool = True,
) -> dict[str, Any]:
    """Reassign, assign, or unassign a Litter-Robot 5 PET_VISIT event."""
    clean_event_id = event_id.strip()
    if not clean_event_id:
        raise HomeAssistantError("event_id must be a non-empty string.")

    from_clean = from_pet.strip() if isinstance(from_pet, str) and from_pet.strip() else None
    to_clean = to_pet.strip() if isinstance(to_pet, str) and to_pet.strip() else None
    if not from_clean and not to_clean:
        raise HomeAssistantError(
            "At least one of 'from_pet' or 'to_pet' must be provided."
        )

    _, lr_coordinator, account = get_litterrobot_runtime(hass)
    robot = resolve_lr5_robot(account, robot_id)

    from_pet_id = resolve_pet_id(account, from_clean) if from_clean else None
    to_pet_id = resolve_pet_id(account, to_clean) if to_clean else None

    body: dict[str, str] = {"eventId": clean_event_id}
    if from_pet_id:
        body["fromPetId"] = from_pet_id
    if to_pet_id:
        body["toPetId"] = to_pet_id

    url = f"{LR5_ENDPOINT}/robots/{robot.serial}/activities"
    try:
        resp_data = await account.session.request("PATCH", url, json=body)
    except ClientResponseError as err:
        raise HomeAssistantError(
            f"Whisker API rejected reassignment for '{clean_event_id}' (HTTP {err.status}): {err.message}"
        ) from err
    except Exception as err:
        raise HomeAssistantError(
            f"Failed to reassign visit '{clean_event_id}': {err}"
        ) from err

    if refresh:
        await lr_coordinator.async_request_refresh()

    action_type = (
        "reassign"
        if (from_pet_id and to_pet_id)
        else ("assign" if to_pet_id else "unassign")
    )
    return {
        "success": True,
        "robot": getattr(robot, "name", None),
        "serial": getattr(robot, "serial", None),
        "event_id": clean_event_id,
        "action": action_type,
        "from_pet_id": from_pet_id,
        "to_pet_id": to_pet_id,
        "response": resp_data,
    }
