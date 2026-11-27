# HA Whisker Pet ID

Home Assistant custom integration (HACS) that exposes **Litter-Robot 5 / 5 Pro** individual `PET_VISIT` events, Pet ID camera clip metadata & presigned download URLs, programmatic visit reassignment (`reassign`, `assign`, `unassign`), and **Gemini / AI Task pet health summaries** with repeat-visit cluster alerts.

It piggybacks directly on Home Assistant's already-authenticated **Whisker (`litterrobot`)** integration and uses your existing Home Assistant **AI Task** entity (e.g. `ai_task.google_ai_task` from Google Generative AI)—no duplicate credentials or separate API keys required.

## Installation (HACS)

1. In Home Assistant, open **HACS** -> **⋮** (top-right) -> **Custom repositories**.
2. Add `https://github.com/bherville/ha-whisker-pet-id` with category **Integration**.
3. Search for **HA Whisker Pet ID**, download `v0.2.0` (or latest), and **Restart Home Assistant**.
4. Go to **Settings -> Devices & Services -> Add Integration**, search **HA Whisker Pet ID**, and click **Submit**.
5. Click **Configure** on the **HA Whisker Pet ID** integration entry to pick your **AI Task entity**, **Notify service** (e.g. `notify.mobile_app_brads_iphone_17`), daily summary schedule, and visit cluster thresholds.

## Exposed Actions

- `ha_whisker_pet_id.get_pets` — Lists all Whisker pet profiles with `pet_id`, `name`, `estimated_weight_lbs`, `last_weight_reading_lbs`, `pet_tag_id`, `image_url`, and recent `weight_history`.
- `ha_whisker_pet_id.list_visits` — Lists recent `PET_VISIT` events (weight, waste type, duration, assigned `pet_ids`, `camera_event_ids`), joins matching camera clips (with `America/Chicago` / HA timezone & pagination support), and flags `unassigned`, `weight_mismatch`, and `scale_anomaly` events.
- `ha_whisker_pet_id.get_clip_urls` — Exchanges a `clip_id` for short-lived presigned S3 MP4 chunk download URLs and signed CloudFront HLS cookies.
- `ha_whisker_pet_id.reassign_visit` — Reassigns (`from_pet` + `to_pet`), assigns (`to_pet`), or unassigns (`from_pet` only) a `PET_VISIT` `event_id` via Whisker's LR5 `PATCH /robots/{serial}/activities` endpoint and refreshes the `litterrobot` coordinator.
- `ha_whisker_pet_id.generate_health_summary` — Computes multi-cat health metrics & cluster checks, calls Home Assistant `ai_task.generate_data` (`ai_task.google_ai_task`) with automatic deterministic fallback, updates all summary sensors, and optionally dispatches push notifications.
- `ha_whisker_pet_id.verify_visits_with_ai` — Evaluates flagged LR5 visits using 0-token Hybrid Fast-Path weight separation + multimodal Gemini Vision (`ref_roster_sheet.jpg` + thumbnail / MP4 video escalation via internal `media_source`), honoring safety guardrails.
- `ha_whisker_pet_id.get_alert_history` — Queries persistent multi-month alert history (`health_cluster`, `health_summary`, `pet_id_review`) filtered by `pet`, `days`, `severity`, `source`, or `active_only`.

## Entities

- `sensor.ha_whisker_pet_id_flagged_visits` — Tracks the count and summary attributes of recent visits with Pet ID anomalies.
- `sensor.ha_whisker_pet_id_ai_pet_id_status` — Shows Auto-Pet-ID mode (`off` / `dry_run` / `auto_reassign` / `backoff`), clean median baselines, action counters, and the last 25 decisions.
- `sensor.ha_whisker_pet_id_alert_history` — Tracks active alert count (`active_alerts`, `recent_alerts` up to 25, and per-cat/source totals across up to 200 persisted events).
- `sensor.ha_whisker_pet_id_health_summary` — Household health status (`normal` / `watch` / `alert`) with `headline`, `summary_markdown`, `alert_pets`, `generation_mode`, and cluster attributes.
- `sensor.ha_whisker_pet_id_<pet>_health_summary` — Per-cat health status, rolling counts, duration/weight metrics, and narrative summary.
- `binary_sensor.ha_whisker_pet_id_health_alert` — Turns `on` (`problem`) when overall health status is `watch`/`alert` or a repeat-visit cluster is detected.

## Built-in Lovelace Custom Cards

When loaded, `ha_whisker_pet_id` automatically serves `/ha_whisker_pet_id/cards.js` via Home Assistant static HTTP paths and `add_extra_js_url` (no manual Lovelace resource entry required). Two cards appear in the visual dashboard card picker and work in YAML dashboards:

- **`custom:whisker-health-archive-card`** — Displays household health status badge, Gemini headline callout, interactive `All` / `Active` / per-cat filter chips (with `/local/ha_whisker_pet_id/pets/<slug>.jpg` avatars), and the persistent alert archive table.
- **`custom:whisker-auto-pet-id-card`** — Displays **Smart Cat ID** status, clean baseline weights per cat with avatars, and a paginated activity log (`page_size`, wide `getGridOptions()` support for Home Assistant Sections dashboards).

Ready-to-paste dashboard stacks pairing these custom cards with native Home Assistant `history-graph`, `logbook`, and cat avatar cards are included under [`dashboards/`](dashboards/).
