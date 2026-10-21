# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

### Changed

- **Breaking:** `helpers.utils.parse_path` returns a flat list of keys and
  indices (`["items", 0, "name"]`) instead of `(key, index)` pairs.
- Property paths support arrays of arrays (`points[0][1]`), root arrays
  (`[0]`) and property names containing `.` or `[`, written as a quoted
  segment (`["a.b"].c`), both in the output and in scenario override keys;
  `helpers.utils.join_path` renders a path the way the generator does.
- Objects and arrays are written to the result as soon as the generator
  enters them, so required empty objects, arrays that draw zero items and
  minimal-mode objects with only optional properties are present, and a
  root array schema produces a list. `scenario_only` mode is unchanged.
- `Context.data` is a live view of the result being built, not a snapshot:
  override callables can observe partly generated data, and reading a
  value that does not exist yet (`KeyError` or `IndexError`) defers the
  override to the second pass.
- Recursive schemas end through a cycle rule (a schema node that recurs on
  the current path is generated with only its required members) instead of
  a depth limit; plain deep nesting is generated in full. `max_depth` is a
  hard cap, now 50 by default, that emits a `UserWarning` when it cuts a
  required property. The scenario and break enumerators share the rule and
  the cap.
- `uniqueItems` is honoured: items are compared as JSON values, closed
  domains (`enum`, `const`, boolean) are sampled without replacement, and an
  unsatisfiable array raises `ValueError`.
- Break scenarios resolve `items[0].name` to the item's schema instead of
  stopping at the array.

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
