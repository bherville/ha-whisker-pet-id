"""Internal Media Source for HA Whisker Pet ID Gemini Vision attachments."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
import time

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MEDIA_STORAGE_DIRNAME

_LOGGER = logging.getLogger(__name__)


def get_media_root(hass: HomeAssistant) -> Path:
    """Return the integration's private media cache directory under .storage."""
    config = getattr(hass, "config", None)
    path_fn = getattr(config, "path", None)
    if callable(path_fn):
        return Path(path_fn(".storage", MEDIA_STORAGE_DIRNAME))
    return Path("/tmp") / MEDIA_STORAGE_DIRNAME


def build_media_source_uri(rel_path: str) -> str:
    """Build a media-source://ha_whisker_pet_id/<rel_path> URI."""
    clean = rel_path.lstrip("/")
    return f"media-source://{DOMAIN}/{clean}"


def guess_mime_type(path: Path) -> str:
    """Infer MIME type for cached JPG/PNG/MP4 attachments."""
    suffix = path.suffix.casefold()
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".mp4":
        return "video/mp4"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def resolve_media_path(root: Path, identifier: str) -> Path:
    """Resolve and validate a relative identifier inside root, blocking traversal."""
    clean = (identifier or "").strip().lstrip("/")
    if not clean or ".." in Path(clean).parts:
        raise Unresolvable(f"Invalid media identifier '{identifier}'.")

    root_resolved = root.resolve()
    candidate = (root_resolved / clean).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise Unresolvable(f"Media identifier escapes cache root: '{identifier}'.")
    if not candidate.is_file():
        raise Unresolvable(f"Cached media file not found: '{identifier}'.")
    return candidate


def cleanup_stale_visit_media(root: Path, max_age_seconds: int = 3600) -> int:
    """Delete leftover temporary visit thumbnails or MP4 chunks older than max_age_seconds."""
    visits_dir = root / "visits"
    if not visits_dir.is_dir():
        return 0
    cutoff = time.time() - max(0, max_age_seconds)
    removed = 0
    for entry in visits_dir.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink(missing_ok=True)
                removed += 1
        except OSError as err:
            _LOGGER.debug("Failed removing stale visit media '%s': %s", entry, err)
    return removed


async def async_get_media_source(hass: HomeAssistant) -> WhiskerPetIdMediaSource:
    """Set up the HA Whisker Pet ID media source."""
    return WhiskerPetIdMediaSource(hass)


class WhiskerPetIdMediaSource(MediaSource):
    """Provide cached Whisker pet reference photos and visit clips to ai_task."""

    name = "HA Whisker Pet ID"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize media source."""
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a cached reference photo or visit clip to a local PlayMedia path."""
        root = get_media_root(self.hass)
        resolved = await self.hass.async_add_executor_job(
            resolve_media_path, root, item.identifier
        )
        mime_type = guess_mime_type(resolved)
        return PlayMedia(url="", mime_type=mime_type, path=resolved)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Return a minimal browse node for internal AI Task media."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title="HA Whisker Pet ID Cache",
            can_play=False,
            can_expand=False,
            children=[],
        )
