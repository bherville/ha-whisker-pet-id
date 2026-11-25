# Changelog

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
