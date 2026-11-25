# Changelog

## 0.1.0

### Minor Changes

- Initial release of HA Whisker Pet ID (`ha_whisker_pet_id`) for Litter-Robot 5 Pro.
- Reuses the authenticated core `litterrobot` integration session without storing duplicate credentials.
- Adds `ha_whisker_pet_id.get_pets`, `ha_whisker_pet_id.list_visits`, `ha_whisker_pet_id.get_clip_urls`, and `ha_whisker_pet_id.reassign_visit` actions with response data.
- Adds diagnostic `sensor.ha_whisker_pet_id_flagged_visits` entity tracking recent unassigned, weight-mismatched, or anomalous-scale visits.
