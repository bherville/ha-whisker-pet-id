# Changelog

## 0.3.2 - 2026-11-27

### Patch Changes

- Sync square-cropped Whisker pet profile avatars into Home Assistant's static `/local/ha_whisker_pet_id/pets/<pet>.jpg` folder (`www/ha_whisker_pet_id/pets/`) with URL-path caching and automatic 24h refresh.
- Expose `entity_picture` on per-cat `sensor.ha_whisker_pet_id_<pet>_health_summary` entities for native dashboard thumbnails.

## 0.3.1 - 2026-11-27

### Patch Changes

- Add persistent historical alert tracking (`alert_history.py`, `.storage/ha_whisker_pet_id.alert_history`, up to 200 entries) surviving Home Assistant restarts and 10-day recorder purges.
- Auto-log and auto-resolve repeat-visit clusters (`health_cluster`), household/per-pet AI summary `watch`/`alert` states (`health_summary`), and uncertain Pet ID review items (`pet_id_review`), emitting `ha_whisker_pet_id_alert` bus events for HA Logbook.
- Add `sensor.ha_whisker_pet_id_alert_history` entity and `ha_whisker_pet_id.get_alert_history` query action (`pet`, `days`, `severity`, `source`, `active_only`, `limit`).

## 0.3.0 - 2026-11-27

### Minor Changes

- Add **Hybrid Fast-Path + Gemini Vision Auto-Pet-ID** (`vision_id.py`) using Home Assistant `ai_task.generate_data` (`ai_task.google_ai_task`) with multimodal `media-source://ha_whisker_pet_id/...` attachments (`media_source.py`) requiring zero `configuration.yaml` setup.
- Cache Whisker pet profile photos into a single labeled reference sheet (`ref_roster_sheet.jpg`) to cut Gemini image token usage ~65%, with Stage 1 clip thumbnail inspection and optional Stage 2 MP4 video chunk escalation (`thumbnail_then_video`).
- Add contamination-resistant median pet weight baselines (`compute_pet_baseline_lbs`, `compute_clean_baselines`) persisted via HA `Store` alongside `processed_event_ids` and a 25-entry decision audit log.
- Add 0-token Hybrid Fast-Path reassignment for unambiguous weight-separated outliers (`>= 0.60 lb` margin, `<= 0.75 lb` target delta) and 0-token auto-unassignment for `< 4.0 lb` scale glitches, plus strict safety gates (`min_confidence`, `max_target_weight_delta_lbs = 1.25`, `429` backoff).
- Add debounced reactive listener (~90s after `litterrobot` updates) + 15m safety-net poll, `ha_whisker_pet_id.verify_visits_with_ai` service action, `sensor.ha_whisker_pet_id_ai_pet_id_status`, and UI/service options.

## 0.2.1 - 2026-11-27

### Patch Changes

- Add `ha_whisker_pet_id.configure_health` action to update and persist AI Task, `notify_service`, schedule, and cluster thresholds directly via service calls.
- Expose configured `notify_service` in `sensor.ha_whisker_pet_id_health_summary` attributes.

## 0.2.0 - 2026-11-27

### Minor Changes

- Integrate Home Assistant AI Task (`ai_task.generate_data`, defaulting to `ai_task.google_ai_task`) for structured veterinary-style Litter-Robot 5 Pro household and per-cat health summaries, with automatic deterministic fallback if Gemini hits quota/spending caps or is unavailable.
- Add repeat-visit cluster detection (sliding window, default `>= 3` visits within `20` minutes) and weight-mismatch caveats in `health.py`.
- Add `WhiskerHealthCoordinator` with configurable options flow (`ai_task_entity`, `notify_service`, daily schedule `summary_hour`/`summary_minute`, cluster sensitivity, and alert cooldown).
- Add household `sensor.ha_whisker_pet_id_health_summary`, per-cat `sensor.ha_whisker_pet_id_<pet>_health_summary` entities, and `binary_sensor.ha_whisker_pet_id_health_alert`.
- Add `ha_whisker_pet_id.generate_health_summary` action with optional response data and push notification dispatch.

## 0.1.1 - 2026-11-25

### Patch Changes

- Raise `DEFAULT_MAX_VALID_WEIGHT_LBS` from `11.1` to `14.0` so larger healthy cats (e.g. `11.4–12.1 lb`) are not flagged as `scale_anomaly`.
- Raise `DEFAULT_MAX_CLIP_DELTA_SECONDS` from `180` to `360` to match longer 3–5 minute LR5 visits.
- Add `signed_time_delta_seconds` to matched clips in `list_visits` and rank pre-exit entry-aligned clips (`~-(duration + 24s)`) ahead of adjacent back-to-back clips.

## 0.1.0

### Minor Changes

- Initial release of HA Whisker Pet ID (`ha_whisker_pet_id`) for Litter-Robot 5 Pro.
- Reuses the authenticated core `litterrobot` integration session without storing duplicate credentials.
- Adds `ha_whisker_pet_id.get_pets`, `ha_whisker_pet_id.list_visits`, `ha_whisker_pet_id.get_clip_urls`, and `ha_whisker_pet_id.reassign_visit` actions with response data.
- Adds diagnostic `sensor.ha_whisker_pet_id_flagged_visits` entity tracking recent unassigned, weight-mismatched, or anomalous-scale visits.
