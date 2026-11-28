# Changelog

## 0.5.3 - 2026-11-27

- **Suppress Stale Mismatches on Reassigned Visits:** Updated `build_health_context` in `health.py` to ignore `weight_mismatch` flags on visits where `is_reassigned: true`, while keeping all visit/weight/cluster telemetry intact and preserving full mismatch detection for all un-reassigned visits.

## 0.5.2 - 2026-11-27

- **Clean Baselines in Health Summaries:** Wired `compute_clean_baselines` (`baseline_overrides`) into `WhiskerHealthCoordinator.async_run_health_summary` and `build_health_context`, and excluded `scale_anomaly` glitches from `suspected_redirected_visits`, eliminating false `Watch` alerts after Smart Cat ID has already resolved misattributions.

## 0.5.1 - 2026-11-27

- **Per-Cat Alert Archive & Clearer Rows:** Refactored `AlertHistoryManager` to record one individual `pet_health:<cat>` alert per flagged cat instead of combining multiple cats into confusing household blobs (automatically pruning legacy multi-cat entries), skips transient startup fallback entries, formats repeat-visit cluster alerts in plain English (`3 quick visits in 16 min (1 with no waste)`), and redesigns `custom:whisker-health-archive-card` to display `Cat | What Happened | Status | When` with circular cat avatars, plain category tags (`Repeat Visits`, `Health Check`, `Cat ID Review`), and responsive narrow-column timestamps.

## 0.5.0 - 2026-11-27

- **On-Demand Fix Pet ID Mismatches Button (`button.ha_whisker_pet_id_fix_pet_id_mismatches`):** Added a native Home Assistant `button` entity under the integration service device so dashboards, automations, scripts, and Assist can trigger Hybrid + Gemini verification & auto-reassignment on recent flagged, un-reassigned visits on demand.
- **Smart Cat ID Quick Action:** Added a **Fix Mismatches** button directly in the header of `custom:whisker-auto-pet-id-card` (configurable or hideable via `fix_button_entity`).

## 0.4.3 - 2026-11-27

- **Expandable Smart Cat ID Rows:** Made every visit row in **Smart Cat ID** (`custom:whisker-auto-pet-id-card`) clickable (and keyboard-accessible) to expand an inline detail drawer showing original vs. verified cat, measured weight vs. baseline difference, method, confidence score, visual match, timestamps, event ID, and full AI/fast-path reasoning.

## 0.4.2 - 2026-11-27

- **Expandable Health Alert Archive Rows:** Removed the `Source` column from `custom:whisker-health-archive-card` and made every alert row clickable (and keyboard-accessible) to expand an inline detail drawer showing the full source (`Repeat-Visit Cluster`, `AI Health Summary`, `Smart Cat ID Review`), severity, timestamps, notified services, and structured alert details.

## 0.4.1 - 2026-11-27

- **Smart Cat ID Polish & Pagination:** Renamed `custom:whisker-auto-pet-id-card` to the friendlier **Smart Cat ID** naming (`Auto-Fix On`, `Weight Match`, `AI Photo` / `AI Video`, `Result` pills), added built-in pagination (`page_size`, `Prev` / `Next` controls) to both built-in cards, implemented `getGridOptions()` (`columns: "full"`) for wide Sections dashboard placement, and added a responsive `@container` layout so narrow columns never clip the rightmost result column.

## 0.4.0 - 2026-11-27

- **Built-in Lovelace Custom Cards:** Automatically serves `/ha_whisker_pet_id/cards.js` and registers `custom:whisker-health-archive-card` (overall status badge, Gemini headline callout, interactive All/Active/per-cat filter chips with local cat avatars, and persistent alert history table) and `custom:whisker-auto-pet-id-card` (Auto-Pet-ID mode badge, counters, clean baseline weight pills with cat avatars, and recent AI/fast-path decision audit table).
- **Bundled Dashboard YAML Templates:** Added ready-to-paste `dashboards/whisker_health_stack.yaml`, `dashboards/whisker_auto_pet_id_stack.yaml`, and `dashboards/cat_avatar_cards.yaml` pairing the built-in custom cards with native Home Assistant `history-graph`, `logbook`, and avatar cards.

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
