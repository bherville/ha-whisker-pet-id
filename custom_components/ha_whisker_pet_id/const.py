"""Constants for HA Whisker Pet ID."""

from __future__ import annotations

DOMAIN = "ha_whisker_pet_id"
LITTERROBOT_DOMAIN = "litterrobot"

LR5_ENDPOINT = "https://ub.prod.iothings.site"
CAMERA_INVENTORY_API = "https://rrntg65uwf.execute-api.us-east-1.amazonaws.com"

DEFAULT_SCAN_INTERVAL_MINUTES = 15
DEFAULT_WEIGHT_MISMATCH_LBS = 0.65
DEFAULT_MAX_VALID_WEIGHT_LBS = 11.1
DEFAULT_MIN_VALID_WEIGHT_LBS = 4.0

SERVICE_GET_PETS = "get_pets"
SERVICE_LIST_VISITS = "list_visits"
SERVICE_GET_CLIP_URLS = "get_clip_urls"
SERVICE_REASSIGN_VISIT = "reassign_visit"
