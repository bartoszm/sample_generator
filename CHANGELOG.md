# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-15

### Added
- **Minimal Mode**: New `minimal_mode` flag in `Scenario` for generating samples with only required properties. When set to `True`, optional properties are omitted unless explicitly referenced by overrides, default_data, or oneof_selectors. This enables cleaner, more focused sample generation for testing required-field validation.
- **Variant Selectors Alias**: Added `variant_selectors` as a read-only property alias for `oneof_selectors`, providing clearer semantics since selectors now apply to both `oneOf` and `anyOf` branches.
- **Nested oneOf Example**: Added comprehensive example (`examples/nested_oneof_example.py`) demonstrating complex nested `oneOf` schemas with 678 lines of detailed usage patterns.
- **Enhanced Utility Functions**: Added `remove_nulls_deep` helper function in `helpers/utils.py` for cleaning generated data structures.

### Changed
- Updated `JSONSchemaGenerator` to support minimal_mode generation logic
- Enhanced documentation in `docs/SCENARIOS.md` with minimal_mode usage examples

### Fixed
- Improved handling of required vs optional properties in sample generation

## [0.2.0] - 2024-01-XX

### Added
- Scenario enumeration and selection strategies
- oneOf selectors for deterministic schema selection
- Enhanced tests for oneOf and allOf behavior
- Developer guide documentation
- Code linting improvements

### Changed
- Updated version to 0.2.0
- Updated copyright year
- Package name consistency in README

## [0.1.0] - Initial Release

### Added
- Initial JSON Schema sample generator implementation
- Default value generator with comprehensive type support
- Schema generator builder pattern
- Support for allOf compositions
- Basic scenario support with overrides
- Comprehensive test suite

[0.3.0]: https://github.com/bartoszm/sample_generator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bartoszm/sample_generator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bartoszm/sample_generator/releases/tag/v0.1.0
