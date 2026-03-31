# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-03-15

### Added
- **Phase 4 — Geography & Addresses** (geo.admin.ch, no API key):
  - `road_geocode_address`: Swiss address to GPS coordinates (official building register)
  - `road_reverse_geocode`: GPS to official address with EGID/EGAID (GWR)
  - `road_classify_road`: Road classification via swissTLM3D

## [0.3.1] - 2026-03-04

### Fixed
- `park_rail.py`: SBB renamed dataset `park-and-rail` causing HTTP 404. Added fallback chain across 3 candidate endpoints with clear error message linking to data.sbb.ch
- `ev_charging.py`: `ChargingStationNames` arrives as `dict` or `list` depending on operator. Fixed with `isinstance` normalization
- `multimodal.py`: `transport.opendata.ch` returns `duration` as string `'HH:MM:SS'`, not integer. Fixed with robust string-to-seconds conversion
- `multimodal.py`: `build_mobility_snapshot()` crashed with `NoneType has no attribute 'get'` when Park+Rail query returned `None`. Added `or {}` guard with fallback empty facilities list
- `server.py`: `road_check_status()` used `HEAD` request for sharedmobility API which only supports `GET`. Fixed to use `GET` for sharedmobility, `HEAD` for others
- `shared_mobility.py`: Documented that `sharedmobility.ch` does not enforce strict radius filtering (API behaviour, no code fix needed)

## [0.3.0] - 2026-03-01

### Added
- **Phase 3 — Park & Rail + Multimodal** (no API key):
  - `road_park_rail`: SBB Park+Rail facilities nearby
  - `road_mobility_snapshot`: Aggregated mobility overview for a location
  - `road_multimodal_plan`: Car to Park+Rail to public transport trip planning
