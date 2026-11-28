"""Hybrid fast-path + multimodal Gemini Vision Pet ID verification."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import shutil
import statistics
import time
from typing import Any
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import (
    async_download_media_file,
    async_get_clip_urls,
    normalize_weight_lbs,
)
from .const import (
    AVATAR_LOCAL_URL_PREFIX,
    AVATAR_WWW_SUBDIR,
    DEFAULT_MAX_TARGET_WEIGHT_DELTA_LBS,
    DEFAULT_MAX_VALID_WEIGHT_LBS,
    DEFAULT_MIN_VALID_WEIGHT_LBS,
    FAST_PATH_MAX_BEST_DELTA_LBS,
    FAST_PATH_MIN_ASSIGNED_DELTA_LBS,
    FAST_PATH_MIN_MARGIN_LBS,
    FAST_PATH_MIN_SECOND_DELTA_LBS,
    SNAPSHOT_LOCAL_URL_PREFIX,
    SNAPSHOT_MAX_FILES,
    SNAPSHOT_WWW_SUBDIR,
    VIDEO_ESCALATION_MODES,
)
from .media_source import build_media_source_uri

_LOGGER = logging.getLogger(__name__)

_REF_TTL_SECONDS = 24 * 3600
_MAX_THUMB_BYTES = 3 * 1024 * 1024
_MAX_VIDEO_CHUNK_BYTES = 6 * 1024 * 1024
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_CONFIDENCE_MIN_SCORE = {"medium": 0.70, "high": 0.85}


class GeminiRateLimitError(HomeAssistantError):
    """Raised when Gemini AI Task returns a quota/rate-limit error."""


def is_rate_limit_error(err: BaseException) -> bool:
    """Return True if an exception message indicates Gemini 429 / quota exhaustion."""
    msg = str(err).casefold()
    return (
        "429" in msg
        or "resource_exhausted" in msg
        or "quota" in msg
        or "spending cap" in msg
        or "rate limit" in msg
    )


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return slug or "item"


def _url_identity_path(url: str) -> str:
    """Return URL scheme/host/path without ephemeral S3 signature query parameters."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def compute_clean_baselines(
    pets: list[dict[str, Any]],
    stored_baselines: dict[str, float] | None = None,
    *,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
    max_valid_weight_lbs: float = DEFAULT_MAX_VALID_WEIGHT_LBS,
) -> dict[str, float]:
    """Compute contamination-resistant median pet weight baselines in pounds."""
    stored = stored_baselines or {}
    baselines: dict[str, float] = {}

    for pet in pets:
        name = str(pet.get("name") or "").strip()
        if not name:
            continue

        valid: list[float] = []
        for item in pet.get("recent_weight_history") or []:
            w_raw = item.get("weight_lbs") if isinstance(item, dict) else None
            if (
                isinstance(w_raw, (int, float))
                and not isinstance(w_raw, bool)
                and min_valid_weight_lbs <= float(w_raw) < max_valid_weight_lbs
            ):
                valid.append(float(w_raw))

        stored_val = stored.get(name)
        has_stored = isinstance(stored_val, (int, float)) and float(stored_val) > 0

        if len(valid) >= 3 and (max(valid) - min(valid)) <= 2.0:
            baselines[name] = round(float(statistics.median(valid)), 2)
        elif has_stored:
            baselines[name] = round(float(stored_val), 2)
        elif valid:
            baselines[name] = round(float(statistics.median(valid)), 2)
        else:
            est = pet.get("estimated_weight_lbs")
            if isinstance(est, (int, float)) and not isinstance(est, bool) and float(est) > 0:
                baselines[name] = round(float(est), 2)

    return baselines


def evaluate_hybrid_fast_path(
    visit: dict[str, Any],
    clean_baselines: dict[str, float],
    *,
    enabled: bool = True,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
    max_valid_weight_lbs: float = DEFAULT_MAX_VALID_WEIGHT_LBS,
) -> dict[str, Any] | None:
    """Return a zero-token decision when scale weight is unambiguously separated."""
    if not enabled or visit.get("is_reassigned") is True:
        return None

    flags = list(visit.get("flags") or [])
    if "weight_mismatch" not in flags and "unassigned" not in flags:
        return None

    weight_lbs = visit.get("weight_lbs")
    if (
        not isinstance(weight_lbs, (int, float))
        or isinstance(weight_lbs, bool)
        or float(weight_lbs) < min_valid_weight_lbs
        or float(weight_lbs) >= max_valid_weight_lbs
    ):
        return None
    w = float(weight_lbs)

    if len(clean_baselines) < 2:
        return None

    ranked = sorted(
        (
            (name, float(base), abs(w - float(base)))
            for name, base in clean_baselines.items()
            if isinstance(base, (int, float)) and float(base) > 0
        ),
        key=lambda item: item[2],
    )
    if len(ranked) < 2:
        return None

    best_name, best_base, best_delta = ranked[0]
    second_name, _second_base, second_delta = ranked[1]

    if best_delta > FAST_PATH_MAX_BEST_DELTA_LBS:
        return None
    if second_delta < FAST_PATH_MIN_SECOND_DELTA_LBS:
        return None
    if (second_delta - best_delta) < FAST_PATH_MIN_MARGIN_LBS:
        return None

    assigned_pets = [str(p) for p in (visit.get("assigned_pets") or []) if p]
    if best_name in assigned_pets:
        return None

    for cur_name in assigned_pets:
        cur_base = clean_baselines.get(cur_name)
        if cur_base is not None and abs(w - float(cur_base)) < FAST_PATH_MIN_ASSIGNED_DELTA_LBS:
            return None

    from_label = ", ".join(assigned_pets) if assigned_pets else "Unassigned"
    return {
        "recommended_pet": best_name,
        "confidence": "high",
        "confidence_score": 0.98,
        "visual_match": "fast_path",
        "needs_video": False,
        "stage": "hybrid_fast_path",
        "reasoning": (
            f"Scale {w:.2f} lb is {best_delta:.2f} lb from {best_name} ({best_base:.2f} lb) "
            f"and {second_delta:.2f} lb from next-closest {second_name} "
            f"(vs {from_label})."
        ),
    }


def _build_roster_sheet_sync(
    items: list[tuple[str, float | None, Path]], sheet_path: Path
) -> bool:
    """Stitch cached pet reference photos into a single labeled roster JPEG."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError:
        return False

    if not items:
        return False

    cols = min(3, len(items))
    rows = (len(items) + cols - 1) // cols
    cell_w = 360
    img_h = 320
    footer_h = 56
    cell_h = img_h + footer_h
    pad = 16

    canvas_w = cols * cell_w + (cols + 1) * pad
    canvas_h = rows * cell_h + (rows + 1) * pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), (24, 27, 34))
    draw = ImageDraw.Draw(canvas)

    font = None
    for font_path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ):
        if Path(font_path).is_file():
            try:
                font = ImageFont.truetype(font_path, 24)
                break
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    for idx, (name, baseline, img_path) in enumerate(items):
        row = idx // cols
        col = idx % cols
        x0 = pad + col * (cell_w + pad)
        y0 = pad + row * (cell_h + pad)

        try:
            with Image.open(img_path) as src:
                rgb = ImageOps.exif_transpose(src).convert("RGB")
                fitted = ImageOps.fit(
                    rgb, (cell_w, img_h), method=Image.Resampling.LANCZOS
                )
        except Exception as err:
            _LOGGER.debug("Failed rendering reference image %s: %s", img_path, err)
            return False

        canvas.paste(fitted, (x0, y0))
        draw.rectangle(
            [x0, y0 + img_h, x0 + cell_w, y0 + cell_h],
            fill=(15, 18, 24),
        )
        draw.rectangle(
            [x0, y0, x0 + cell_w - 1, y0 + cell_h - 1],
            outline=(70, 78, 92),
            width=2,
        )
        label = f"{name} ({baseline:.2f} lb)" if baseline is not None else name
        draw.text((x0 + 14, y0 + img_h + 14), label, fill=(245, 247, 250), font=font)

    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = sheet_path.with_suffix(".tmp.jpg")
    canvas.save(tmp_path, format="JPEG", quality=88, optimize=True)
    tmp_path.replace(sheet_path)
    return True


async def async_prepare_reference_attachments(
    hass: HomeAssistant,
    websession: Any,
    pets: list[dict[str, Any]],
    clean_baselines: dict[str, float],
    media_root: Path,
    *,
    force_refresh: bool = False,
) -> tuple[list[dict[str, str]], bool, list[str]]:
    """Cache Whisker pet reference photos and return AI Task media attachments."""
    refs_dir = media_root / "refs"
    await hass.async_add_executor_job(
        lambda: refs_dir.mkdir(parents=True, exist_ok=True)
    )

    now = time.time()
    cached_items: list[tuple[str, float | None, Path]] = []
    any_ref_updated = False

    for pet in pets:
        name = str(pet.get("name") or "").strip()
        image_url = pet.get("image_url")
        if not name or not isinstance(image_url, str) or not image_url.strip():
            continue

        slug = _safe_slug(name.lower())
        img_path = refs_dir / f"ref_{slug}.jpg"
        meta_path = refs_dir / f"ref_{slug}.url"
        url_id = _url_identity_path(image_url)

        needs_fetch = force_refresh or not img_path.is_file()
        if not needs_fetch:
            try:
                age = now - img_path.stat().st_mtime
                prev_url = meta_path.read_text(encoding="utf-8").strip() if meta_path.is_file() else ""
                if age > _REF_TTL_SECONDS or prev_url != url_id:
                    needs_fetch = True
            except OSError:
                needs_fetch = True

        if needs_fetch and websession is not None:
            try:
                await async_download_media_file(
                    hass,
                    websession,
                    image_url,
                    img_path,
                    max_bytes=5 * 1024 * 1024,
                )
                await hass.async_add_executor_job(
                    meta_path.write_text, url_id, "utf-8"
                )
                any_ref_updated = True
            except Exception as err:
                _LOGGER.debug("Failed refreshing reference photo for %s: %s", name, err)

        if img_path.is_file():
            cached_items.append((name, clean_baselines.get(name), img_path))

    if not cached_items:
        return [], False, []

    sheet_path = refs_dir / "ref_roster_sheet.jpg"
    sheet_stale = (
        any_ref_updated
        or force_refresh
        or not sheet_path.is_file()
        or (now - sheet_path.stat().st_mtime > _REF_TTL_SECONDS)
    )
    sheet_ok = sheet_path.is_file()
    if sheet_stale:
        sheet_ok = await hass.async_add_executor_job(
            _build_roster_sheet_sync, cached_items, sheet_path
        )

    pet_names = [item[0] for item in cached_items]
    if sheet_ok and sheet_path.is_file():
        return (
            [
                {
                    "media_content_id": build_media_source_uri("refs/ref_roster_sheet.jpg"),
                    "media_content_type": "image/jpeg",
                }
            ],
            True,
            pet_names,
        )

    return (
        [
            {
                "media_content_id": build_media_source_uri(f"refs/{path.name}"),
                "media_content_type": "image/jpeg",
            }
            for _name, _base, path in cached_items
        ],
        False,
        pet_names,
    )


def get_avatar_www_dir(hass: HomeAssistant) -> Path:
    """Return Home Assistant's static www/ha_whisker_pet_id/pets directory."""
    config = getattr(hass, "config", None)
    path_fn = getattr(config, "path", None)
    if callable(path_fn):
        return Path(path_fn("www", AVATAR_WWW_SUBDIR))
    return Path("/tmp") / AVATAR_WWW_SUBDIR


def _crop_square_avatar_sync(src_path: Path, dest_path: Path, size: int = 256) -> bool:
    """Save a square-cropped JPEG avatar, or copy bytes directly if Pillow is unavailable."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(".tmp.jpg")
    try:
        from PIL import Image, ImageOps

        with Image.open(src_path) as src:
            rgb = ImageOps.exif_transpose(src).convert("RGB")
            cropped = ImageOps.fit(rgb, (size, size), method=Image.Resampling.LANCZOS)
            cropped.save(tmp_path, format="JPEG", quality=90, optimize=True)
        tmp_path.replace(dest_path)
        return True
    except ImportError:
        shutil.copyfile(src_path, tmp_path)
        tmp_path.replace(dest_path)
        return True
    except Exception as err:
        _LOGGER.debug("Failed processing avatar %s: %s", src_path, err)
        tmp_path.unlink(missing_ok=True)
        return False


async def async_sync_pet_avatars(
    hass: HomeAssistant,
    websession: Any,
    pets: list[dict[str, Any]],
    *,
    force_refresh: bool = False,
) -> dict[str, str]:
    """Cache square Whisker pet avatars under www/ and return /local URL map."""
    avatar_dir = get_avatar_www_dir(hass)
    await hass.async_add_executor_job(
        lambda: avatar_dir.mkdir(parents=True, exist_ok=True)
    )

    now = time.time()
    avatars: dict[str, str] = {}

    for pet in pets:
        name = str(pet.get("name") or "").strip()
        image_url = pet.get("image_url")
        if not name:
            continue

        slug = _safe_slug(name.lower())
        dest_path = avatar_dir / f"{slug}.jpg"
        meta_path = avatar_dir / f"{slug}.url"

        if isinstance(image_url, str) and image_url.strip():
            url_id = _url_identity_path(image_url)
            needs_fetch = force_refresh or not dest_path.is_file()
            if not needs_fetch:
                try:
                    age = now - dest_path.stat().st_mtime
                    prev_url = (
                        meta_path.read_text(encoding="utf-8").strip()
                        if meta_path.is_file()
                        else ""
                    )
                    if age > _REF_TTL_SECONDS or prev_url != url_id:
                        needs_fetch = True
                except OSError:
                    needs_fetch = True

            if needs_fetch and websession is not None:
                raw_tmp = avatar_dir / f".raw_{slug}.jpg"
                try:
                    await async_download_media_file(
                        hass,
                        websession,
                        image_url,
                        raw_tmp,
                        max_bytes=5 * 1024 * 1024,
                    )
                    ok = await hass.async_add_executor_job(
                        _crop_square_avatar_sync, raw_tmp, dest_path
                    )
                    if ok:
                        await hass.async_add_executor_job(
                            meta_path.write_text, url_id, "utf-8"
                        )
                except Exception as err:
                    _LOGGER.debug("Failed syncing local avatar for %s: %s", name, err)
                finally:
                    await hass.async_add_executor_job(
                        raw_tmp.unlink, True
                    )

        if dest_path.is_file():
            avatars[name] = f"{AVATAR_LOCAL_URL_PREFIX}/{slug}.jpg"

    return avatars


def get_snapshot_www_dir(hass: HomeAssistant) -> Path:
    """Return Home Assistant's static www/ha_whisker_pet_id/snapshots directory."""
    config = getattr(hass, "config", None)
    path_fn = getattr(config, "path", None)
    if callable(path_fn):
        return Path(path_fn("www", SNAPSHOT_WWW_SUBDIR))
    return Path("/tmp") / SNAPSHOT_WWW_SUBDIR


def _write_bytes_sync(dest_path: Path, payload: bytes) -> None:
    """Atomically write JPEG bytes to a static file path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(".tmp.jpg")
    tmp_path.write_bytes(payload)
    tmp_path.replace(dest_path)


def _prune_snapshots_sync(snap_dir: Path, max_files: int = SNAPSHOT_MAX_FILES) -> int:
    """Keep only the newest max_files JPEG snapshots under snap_dir."""
    if not snap_dir.is_dir():
        return 0
    files: list[tuple[float, Path]] = []
    for path in snap_dir.glob("*.jpg"):
        if not path.is_file():
            continue
        try:
            files.append((path.stat().st_mtime, path))
        except OSError:
            continue
    files.sort(key=lambda item: item[0], reverse=True)
    removed = 0
    for _, stale_path in files[max(1, max_files) :]:
        try:
            stale_path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed


async def async_save_visit_snapshots(
    hass: HomeAssistant,
    websession: Any,
    visit: dict[str, Any],
    *,
    camera_entity_id: str = "",
    capture_live_camera: bool = False,
    robot_label: str = "Litter-Robot",
    max_files: int = SNAPSHOT_MAX_FILES,
) -> list[dict[str, str]]:
    """Save bounded freeze-frame snapshots (LR5 + optional HA room camera)."""
    raw_id = str(visit.get("event_id") or visit.get("local_time") or "visit")
    safe_eid = _safe_slug(raw_id)
    snap_dir = get_snapshot_www_dir(hass)
    clean_robot_label = (robot_label or "").strip() or "Litter-Robot"
    snapshots: list[dict[str, str]] = []
    wrote_file = False

    # 1. Litter-Robot visit thumbnail
    lr5_filename = f"visit_{safe_eid}_lr5.jpg"
    lr5_path = snap_dir / lr5_filename
    clip = _extract_primary_clip(visit)
    thumb_url = clip.get("thumbnail_url") if isinstance(clip, dict) else None

    if lr5_path.is_file() and lr5_path.stat().st_size > 0:
        snapshots.append(
            {
                "label": clean_robot_label,
                "url": f"{SNAPSHOT_LOCAL_URL_PREFIX}/{lr5_filename}",
            }
        )
    elif isinstance(thumb_url, str) and thumb_url.strip() and websession is not None:
        try:
            await async_download_media_file(
                hass, websession, thumb_url, lr5_path, max_bytes=_MAX_THUMB_BYTES
            )
            if lr5_path.is_file() and lr5_path.stat().st_size > 0:
                wrote_file = True
                snapshots.append(
                    {
                        "label": clean_robot_label,
                        "url": f"{SNAPSHOT_LOCAL_URL_PREFIX}/{lr5_filename}",
                    }
                )
        except Exception as err:
            _LOGGER.debug("Failed saving LR5 freeze-frame for %s: %s", raw_id, err)

    # 2. Optional Home Assistant room camera snapshot
    cam_eid = (camera_entity_id or "").strip()
    if cam_eid:
        cam_filename = f"visit_{safe_eid}_cam.jpg"
        cam_path = snap_dir / cam_filename
        states = getattr(hass, "states", None)
        cam_state = states.get(cam_eid) if states is not None and hasattr(states, "get") else None
        cam_label = str(
            (getattr(cam_state, "attributes", None) or {}).get("friendly_name")
            or cam_eid
        )
        if cam_path.is_file() and cam_path.stat().st_size > 0:
            snapshots.append(
                {
                    "label": cam_label,
                    "url": f"{SNAPSHOT_LOCAL_URL_PREFIX}/{cam_filename}",
                }
            )
        elif capture_live_camera:
            try:
                from homeassistant.components.camera import async_get_image

                img = await async_get_image(hass, cam_eid)
                content = getattr(img, "content", None)
                if isinstance(content, (bytes, bytearray)) and len(content) > 0:
                    await hass.async_add_executor_job(
                        _write_bytes_sync, cam_path, bytes(content)
                    )
                    wrote_file = True
                    snapshots.append(
                        {
                            "label": cam_label,
                            "url": f"{SNAPSHOT_LOCAL_URL_PREFIX}/{cam_filename}",
                        }
                    )
            except Exception as err:
                _LOGGER.debug("Failed capturing HA camera snapshot %s: %s", cam_eid, err)

    if wrote_file:
        try:
            await hass.async_add_executor_job(
                _prune_snapshots_sync, snap_dir, max(1, int(max_files))
            )
        except Exception as err:
            _LOGGER.debug("Failed pruning snapshots in %s: %s", snap_dir, err)

    return snapshots


def _format_roster_lines(
    pets: list[dict[str, Any]],
    clean_baselines: dict[str, float],
    *,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
    max_valid_weight_lbs: float = DEFAULT_MAX_VALID_WEIGHT_LBS,
) -> str:
    lines: list[str] = []
    for pet in pets:
        name = str(pet.get("name") or "").strip()
        if not name:
            continue
        base = clean_baselines.get(name)
        valid_hist = [
            round(float(h["weight_lbs"]), 2)
            for h in (pet.get("recent_weight_history") or [])
            if isinstance(h, dict)
            and isinstance(h.get("weight_lbs"), (int, float))
            and min_valid_weight_lbs <= float(h["weight_lbs"]) < max_valid_weight_lbs
        ]
        hist_range = (
            f"{min(valid_hist):.2f}-{max(valid_hist):.2f} lb"
            if valid_hist
            else "no recent clean range"
        )
        breeds = ", ".join(pet.get("breeds") or []) or "unknown breed"
        gender = pet.get("gender") or "unknown"
        base_str = f"{base:.2f} lb" if base is not None else "unknown"
        lines.append(
            f"- {name}: clean baseline {base_str} (recent {hist_range}), {gender}, {breeds}"
        )
    return "\n".join(lines)


def _extract_primary_clip(visit: dict[str, Any]) -> dict[str, Any] | None:
    for clip in visit.get("matched_clips") or []:
        if isinstance(clip, dict) and (clip.get("clip_id") or clip.get("thumbnail_url")):
            return clip
    return None


def _build_vision_instructions(
    visit: dict[str, Any],
    pets: list[dict[str, Any]],
    clean_baselines: dict[str, float],
    *,
    uses_roster_sheet: bool,
    ref_pet_order: list[str],
    stage: str,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
    max_valid_weight_lbs: float = DEFAULT_MAX_VALID_WEIGHT_LBS,
) -> str:
    roster_text = _format_roster_lines(
        pets,
        clean_baselines,
        min_valid_weight_lbs=min_valid_weight_lbs,
        max_valid_weight_lbs=max_valid_weight_lbs,
    )
    clip = _extract_primary_clip(visit) or {}
    detections = [
        d.get("petName") or d.get("petId")
        for d in (clip.get("pet_detections") or [])
        if isinstance(d, dict)
    ]
    assigned = ", ".join(visit.get("assigned_pets") or []) or "UNASSIGNED"
    closest = ", ".join(
        f"{c.get('name')} ({c.get('baseline_lbs')} lb, delta {c.get('delta_lbs'):+.2f})"
        for c in (visit.get("closest_pets_by_weight") or [])[:3]
        if c.get("name") and c.get("baseline_lbs") is not None
    )

    if uses_roster_sheet:
        ref_desc = (
            "Attachment 1 is a labeled reference sheet grid showing every household cat's name "
            "and baseline weight below its photo."
        )
    else:
        ref_desc = (
            f"The first {len(ref_pet_order)} image attachments are pet reference photos in order: "
            f"{', '.join(ref_pet_order)}."
        )

    stage_note = (
        "The final attachment is the Litter-Robot entry/exit thumbnail for this visit. "
        "If the cat is distant, blurry, obscured, nighttime IR makes coat colors ambiguous, or multiple cats appear, set needs_video='true'."
        if stage == "thumbnail"
        else "Stage 1 thumbnail was inconclusive. The final attachments are entry and interior MP4 video clips from this visit — identify the cat that actually enters and uses the Litter-Robot globe."
    )

    return (
        "You are verifying Litter-Robot Pet ID attribution from camera media and scale weight.\n"
        f"{ref_desc}\n"
        f"{stage_note}\n\n"
        "Household Cats:\n"
        f"{roster_text}\n\n"
        "Visit Telemetry:\n"
        f"- Local time: {visit.get('local_time') or visit.get('timestamp')}\n"
        f"- Scale weight: {visit.get('weight_lbs')} lb (waste {visit.get('waste_type')} / {visit.get('waste_weight')}g)\n"
        f"- Duration: {visit.get('duration_seconds')}s\n"
        f"- Whisker currently assigned pet: {assigned} (NOTE: Whisker camera AI can mislabel short visits or confuse similarly colored cats; verify independently against the reference photos and weight.)\n"
        f"- Whisker clip detections: {detections or ['none']}\n"
        f"- Closest by clean weight: {closest or 'none'}\n"
        f"- Flags: {visit.get('flags') or []}\n\n"
        "Rules:\n"
        "1. Rely primarily on the actual visual appearance (coat colors, markings, ear/face shape, tail, and body build) compared against the reference photos, cross-checked against scale weight.\n"
        "2. Do NOT blindly trust Whisker's assigned pet or clip detection.\n"
        "3. In recommended_pet, return the exact cat name from the household list, or 'KEEP' if already right, or 'UNCERTAIN' if you cannot tell.\n"
        "4. Return confidence ('high'|'medium'|'low'), confidence_score (0.0-1.0), visual_match ('clear'|'partial'|'unclear'|'no_cat_visible'), needs_video ('true'|'false'), and concise 1-2 sentence reasoning."
    )


def _parse_bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in ("true", "yes", "1", "y")
    return False


def _parse_vision_response(
    raw_data: Any,
    known_pets: list[str],
    *,
    stage: str,
) -> dict[str, Any]:
    if not isinstance(raw_data, dict):
        raise ValueError("ai_task.generate_data returned non-dict response")

    lookup = {name.casefold(): name for name in known_pets}
    raw_rec = str(raw_data.get("recommended_pet") or "").strip()
    rec_cf = raw_rec.casefold()
    if rec_cf in lookup:
        recommended = lookup[rec_cf]
    elif rec_cf in ("keep", "uncertain", "unassign"):
        recommended = raw_rec.upper()
    else:
        recommended = "UNCERTAIN"

    conf_raw = str(raw_data.get("confidence") or "low").strip().casefold()
    confidence = conf_raw if conf_raw in _CONFIDENCE_RANK else "low"

    raw_score = raw_data.get("confidence_score")
    try:
        score = max(0.0, min(1.0, float(raw_score)))
    except (TypeError, ValueError):
        score = {"high": 0.90, "medium": 0.72, "low": 0.40}[confidence]

    vm_raw = str(raw_data.get("visual_match") or "unclear").strip().casefold()
    visual_match = (
        vm_raw
        if vm_raw in ("clear", "partial", "unclear", "no_cat_visible")
        else "unclear"
    )
    needs_video = _parse_bool_flag(raw_data.get("needs_video"))
    reasoning = str(raw_data.get("reasoning") or "").strip() or "No reasoning provided."

    return {
        "recommended_pet": recommended,
        "confidence": confidence,
        "confidence_score": round(score, 2),
        "visual_match": visual_match,
        "needs_video": needs_video,
        "stage": stage,
        "reasoning": reasoning,
    }


def _select_video_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select up to 2 representative MP4 chunks (entry + interior/exit)."""
    valid = [c for c in chunks if isinstance(c, dict) and c.get("download_url")]
    if not valid:
        return []
    if len(valid) == 1:
        return [valid[0]]
    second_idx = len(valid) - 2 if len(valid) >= 3 else 1
    if second_idx == 0:
        return [valid[0]]
    return [valid[0], valid[second_idx]]


async def _async_call_gemini_vision(
    hass: HomeAssistant,
    *,
    ai_task_entity: str,
    instructions: str,
    attachments: list[dict[str, str]],
    known_pets: list[str],
    stage: str,
) -> dict[str, Any]:
    structure = {
        "recommended_pet": {
            "description": "Exact cat name from roster, KEEP, UNASSIGN, or UNCERTAIN",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "confidence": {
            "description": "Confidence level: high, medium, or low",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "confidence_score": {
            "description": "Numeric confidence score between 0.0 and 1.0",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "visual_match": {
            "description": "Visual clarity: clear, partial, unclear, or no_cat_visible",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "needs_video": {
            "description": "true if thumbnail is ambiguous and MP4 video should be checked, else false",
            "required": True,
            "selector": {"text": {"multiline": False}},
        },
        "reasoning": {
            "description": "1-2 concise sentences explaining coat markings and scale weight match",
            "required": True,
            "selector": {"text": {"multiline": True}},
        },
    }

    try:
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": ai_task_entity,
                "task_name": "Whisker Pet ID Verification",
                "instructions": instructions,
                "structure": structure,
                "attachments": attachments,
            },
            blocking=True,
            return_response=True,
        )
    except Exception as err:
        if is_rate_limit_error(err):
            raise GeminiRateLimitError(str(err)) from err
        raise

    raw_data = response.get("data") if isinstance(response, dict) else response
    return _parse_vision_response(raw_data, known_pets, stage=stage)


async def async_verify_visit_with_gemini(
    hass: HomeAssistant,
    websession: Any,
    visit: dict[str, Any],
    pets: list[dict[str, Any]],
    clean_baselines: dict[str, float],
    ref_attachments: list[dict[str, str]],
    *,
    uses_roster_sheet: bool,
    ref_pet_order: list[str],
    media_root: Path,
    ai_task_entity: str,
    video_escalation: str = "thumbnail_then_video",
    robot_id: str | None = None,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
    max_valid_weight_lbs: float = DEFAULT_MAX_VALID_WEIGHT_LBS,
) -> dict[str, Any]:
    """Run Stage 1 thumbnail verification and optional Stage 2 MP4 video escalation."""
    if not (ai_task_entity or "").strip():
        return {
            "recommended_pet": "UNCERTAIN",
            "confidence": "low",
            "confidence_score": 0.0,
            "visual_match": "unclear",
            "needs_video": False,
            "stage": "unavailable",
            "reasoning": "No AI Task entity is configured in HA Whisker Pet ID options.",
        }

    if not hass.services.has_service("ai_task", "generate_data"):
        return {
            "recommended_pet": "UNCERTAIN",
            "confidence": "low",
            "confidence_score": 0.0,
            "visual_match": "unclear",
            "needs_video": False,
            "stage": "unavailable",
            "reasoning": "Home Assistant ai_task.generate_data service is unavailable.",
        }

    if not ref_attachments:
        return {
            "recommended_pet": "UNCERTAIN",
            "confidence": "low",
            "confidence_score": 0.0,
            "visual_match": "unclear",
            "needs_video": False,
            "stage": "no_references",
            "reasoning": "No cached Whisker pet reference photos available.",
        }

    clip = _extract_primary_clip(visit)
    if clip is None:
        return {
            "recommended_pet": "UNCERTAIN",
            "confidence": "low",
            "confidence_score": 0.0,
            "visual_match": "no_cat_visible",
            "needs_video": False,
            "stage": "no_clip",
            "reasoning": "No matching LR5 camera clip available for visual verification.",
        }

    known_pets = [str(p.get("name")) for p in pets if p.get("name")]
    safe_eid = _safe_slug(str(visit.get("event_id") or "visit"))
    visits_dir = media_root / "visits"
    created_files: list[Path] = []

    try:
        thumb_url = clip.get("thumbnail_url")
        stage1_result: dict[str, Any] | None = None

        if isinstance(thumb_url, str) and thumb_url.strip():
            thumb_rel = f"visits/visit_{safe_eid}_thumb.jpg"
            thumb_path = media_root / thumb_rel
            await async_download_media_file(
                hass, websession, thumb_url, thumb_path, max_bytes=_MAX_THUMB_BYTES
            )
            created_files.append(thumb_path)

            thumb_attachment = {
                "media_content_id": build_media_source_uri(thumb_rel),
                "media_content_type": "image/jpeg",
            }
            instructions1 = _build_vision_instructions(
                visit,
                pets,
                clean_baselines,
                uses_roster_sheet=uses_roster_sheet,
                ref_pet_order=ref_pet_order,
                stage="thumbnail",
                min_valid_weight_lbs=min_valid_weight_lbs,
                max_valid_weight_lbs=max_valid_weight_lbs,
            )
            stage1_result = await _async_call_gemini_vision(
                hass,
                ai_task_entity=ai_task_entity,
                instructions=instructions1,
                attachments=[*ref_attachments, thumb_attachment],
                known_pets=known_pets,
                stage="gemini_thumbnail",
            )

        esc_mode = (
            video_escalation
            if video_escalation in VIDEO_ESCALATION_MODES
            else "thumbnail_then_video"
        )
        should_escalate = (
            esc_mode == "thumbnail_then_video"
            and bool(clip.get("clip_id"))
            and (
                stage1_result is None
                or stage1_result.get("needs_video")
                or stage1_result.get("confidence") != "high"
                or stage1_result.get("visual_match") in ("unclear", "no_cat_visible")
            )
        )

        if not should_escalate:
            return stage1_result or {
                "recommended_pet": "UNCERTAIN",
                "confidence": "low",
                "confidence_score": 0.0,
                "visual_match": "no_cat_visible",
                "needs_video": False,
                "stage": "no_clip",
                "reasoning": "Clip has neither thumbnail_url nor clip_id.",
            }

        try:
            clip_urls = await async_get_clip_urls(
                hass, clip_id=str(clip["clip_id"]), robot_id=robot_id
            )
            selected = _select_video_chunks(clip_urls.get("chunks") or [])
            video_attachments: list[dict[str, str]] = []
            for idx, chunk in enumerate(selected):
                chunk_rel = f"visits/visit_{safe_eid}_c{idx}.mp4"
                chunk_path = media_root / chunk_rel
                try:
                    await async_download_media_file(
                        hass,
                        websession,
                        str(chunk["download_url"]),
                        chunk_path,
                        max_bytes=_MAX_VIDEO_CHUNK_BYTES,
                    )
                except HomeAssistantError as chunk_err:
                    _LOGGER.debug(
                        "Skipping video chunk %s for visit %s: %s",
                        idx,
                        safe_eid,
                        chunk_err,
                    )
                    continue
                created_files.append(chunk_path)
                video_attachments.append(
                    {
                        "media_content_id": build_media_source_uri(chunk_rel),
                        "media_content_type": "video/mp4",
                    }
                )

            if video_attachments:
                instructions2 = _build_vision_instructions(
                    visit,
                    pets,
                    clean_baselines,
                    uses_roster_sheet=uses_roster_sheet,
                    ref_pet_order=ref_pet_order,
                    stage="video",
                    min_valid_weight_lbs=min_valid_weight_lbs,
                    max_valid_weight_lbs=max_valid_weight_lbs,
                )
                return await _async_call_gemini_vision(
                    hass,
                    ai_task_entity=ai_task_entity,
                    instructions=instructions2,
                    attachments=[*ref_attachments, *video_attachments],
                    known_pets=known_pets,
                    stage="gemini_video",
                )
        except GeminiRateLimitError:
            raise
        except Exception as esc_err:
            _LOGGER.warning(
                "Stage 2 video escalation failed for visit %s: %s", safe_eid, esc_err
            )

        if stage1_result is not None:
            return stage1_result

        return {
            "recommended_pet": "UNCERTAIN",
            "confidence": "low",
            "confidence_score": 0.0,
            "visual_match": "unclear",
            "needs_video": False,
            "stage": "gemini_video_failed",
            "reasoning": "Could not verify thumbnail or MP4 clip.",
        }
    finally:
        if created_files:
            def _cleanup() -> None:
                for path in created_files:
                    path.unlink(missing_ok=True)
                if visits_dir.is_dir():
                    for extra in visits_dir.glob(f"visit_{safe_eid}_*"):
                        extra.unlink(missing_ok=True)

            await hass.async_add_executor_job(_cleanup)


def evaluate_reassignment_safety(
    decision: dict[str, Any],
    visit: dict[str, Any],
    clean_baselines: dict[str, float],
    *,
    mode: str,
    min_confidence: str = "high",
    max_target_weight_delta_lbs: float = DEFAULT_MAX_TARGET_WEIGHT_DELTA_LBS,
    min_valid_weight_lbs: float = DEFAULT_MIN_VALID_WEIGHT_LBS,
) -> dict[str, Any]:
    """Apply confidence, visual clarity, and weight-plausibility gates before mutating."""
    assigned_pets = [str(p) for p in (visit.get("assigned_pets") or []) if p]
    from_pet = assigned_pets[0] if assigned_pets else None
    rec = str(decision.get("recommended_pet") or "UNCERTAIN")
    stage = str(decision.get("stage") or "unknown")
    confidence = str(decision.get("confidence") or "low").casefold()
    score = float(decision.get("confidence_score") or 0.0)
    visual_match = str(decision.get("visual_match") or "unclear").casefold()
    weight_lbs = visit.get("weight_lbs")

    if rec == "KEEP" or (rec in clean_baselines and rec in assigned_pets):
        return {
            "action": "keep",
            "from_pet": from_pet,
            "to_pet": from_pet,
            "reason": "Verified current assignment matches.",
        }

    if rec == "UNASSIGN":
        if not from_pet:
            return {
                "action": "keep",
                "from_pet": None,
                "to_pet": None,
                "reason": "Visit is already unassigned.",
            }
        action = "dry_run_unassign" if mode == "dry_run" else "unassign"
        return {
            "action": action,
            "from_pet": from_pet,
            "to_pet": None,
            "reason": decision.get("reasoning", "Recommended unassignment."),
        }

    if rec == "UNCERTAIN" or rec not in clean_baselines:
        return {
            "action": "needs_review",
            "from_pet": from_pet,
            "to_pet": None,
            "reason": decision.get("reasoning", "Uncertain Pet ID."),
        }

    if (
        isinstance(weight_lbs, (int, float))
        and not isinstance(weight_lbs, bool)
        and float(weight_lbs) < min_valid_weight_lbs
    ):
        return {
            "action": "needs_review",
            "from_pet": from_pet,
            "to_pet": rec,
            "reason": f"Blocked assigning {float(weight_lbs):.2f} lb scale anomaly to {rec}.",
        }

    req_conf = min_confidence if min_confidence in _CONFIDENCE_RANK else "high"
    if _CONFIDENCE_RANK.get(confidence, 0) < _CONFIDENCE_RANK[req_conf] or score < _CONFIDENCE_MIN_SCORE[req_conf]:
        return {
            "action": "needs_review",
            "from_pet": from_pet,
            "to_pet": rec,
            "reason": f"Confidence {confidence} ({score:.2f}) below {req_conf} threshold.",
        }

    if stage != "hybrid_fast_path" and visual_match in ("unclear", "no_cat_visible"):
        return {
            "action": "needs_review",
            "from_pet": from_pet,
            "to_pet": rec,
            "reason": f"Visual match '{visual_match}' too weak for auto-reassignment.",
        }

    target_base = clean_baselines.get(rec)
    if (
        isinstance(weight_lbs, (int, float))
        and not isinstance(weight_lbs, bool)
        and target_base is not None
        and abs(float(weight_lbs) - float(target_base)) > max_target_weight_delta_lbs
    ):
        return {
            "action": "needs_review",
            "from_pet": from_pet,
            "to_pet": rec,
            "reason": (
                f"Target {rec} ({target_base:.2f} lb) differs by "
                f"{abs(float(weight_lbs) - float(target_base)):.2f} lb from scale {float(weight_lbs):.2f} lb; needs review."
            ),
        }

    base_action = "reassign" if from_pet else "assign"
    final_action = f"dry_run_{base_action}" if mode == "dry_run" else base_action
    return {
        "action": final_action,
        "from_pet": from_pet,
        "to_pet": rec,
        "reason": decision.get("reasoning", "Passed all Pet ID safety gates."),
    }
