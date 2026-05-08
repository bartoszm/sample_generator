# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog.

## [0.5.0] - 2026-05-07

### Added

- Added `generator_max_items` to `JSONSchemaGenerator` to cap generated
  array sizes globally.
- Added `Schema.from_oas` factory support for OpenAPI schema loading.
- Added dedicated OpenAPI and generator cap documentation in `README.md`
  and `docs/OPENAPI.md`.
- Added tests covering global array size caps and OpenAPI loading behavior.

### Fixed

- Added warning/handling around `jsonref` caching edge cases in OpenAPI
  schema resolution.

## [0.4.0] - 2026-04-26

### Added

- Added break scenario APIs for generating invalid samples for negative tests.

## [0.3.0] - 2026-04-23

### Added

- Added `minimal_mode` to `Scenario` for required-only sample generation.

## [0.2.0] - 2026-04-21

### Added

- Added scenario enumeration and selection strategies.

## [0.1.0] - 2026-04-20

### Added

- Initial alpha release.
