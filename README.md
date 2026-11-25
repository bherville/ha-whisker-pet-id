# HA Whisker Pet ID

Home Assistant custom integration (HACS) that exposes **Litter-Robot 5 / 5 Pro** individual `PET_VISIT` events, Pet ID camera clip metadata & presigned download URLs, and programmatic visit reassignment (`reassign`, `assign`, `unassign`).

It piggybacks directly on Home Assistant's already-authenticated **Whisker (`litterrobot`)** integration—no extra credentials required.

## Installation (HACS)

1. In Home Assistant, open **HACS** -> **⋮** (top-right) -> **Custom repositories**.
2. Add `https://github.com/bherville/ha-whisker-pet-id` with category **Integration**.
3. Search for **HA Whisker Pet ID**, download `v0.1.0` (or latest), and **Restart Home Assistant**.
4. Go to **Settings -> Devices & Services -> Add Integration**, search **HA Whisker Pet ID**, and click **Submit**.

## Exposed Actions (with Response Data)

- `ha_whisker_pet_id.get_pets` — Lists all Whisker pet profiles with `pet_id`, `name`, `estimated_weight_lbs`, `last_weight_reading_lbs`, `pet_tag_id`, `image_url`, and recent `weight_history`.
- `ha_whisker_pet_id.list_visits` — Lists recent `PET_VISIT` events (weight, waste type, duration, assigned `pet_ids`, `camera_event_ids`), joins matching camera clips (with `America/Chicago` / HA timezone & pagination support), and flags `unassigned`, `weight_mismatch`, and `scale_anomaly` events.
- `ha_whisker_pet_id.get_clip_urls` — Exchanges a `clip_id` for short-lived presigned S3 MP4 chunk download URLs and signed CloudFront HLS cookies.
- `ha_whisker_pet_id.reassign_visit` — Reassigns (`from_pet` + `to_pet`), assigns (`to_pet`), or unassigns (`from_pet` only) a `PET_VISIT` `event_id` via Whisker's LR5 `PATCH /robots/{serial}/activities` endpoint and refreshes the `litterrobot` coordinator.

## Diagnostic Sensor

- `Flagged visits` (`sensor.ha_whisker_pet_id_flagged_visits`) — Tracks the count and summary attributes of recent visits with Pet ID anomalies.
