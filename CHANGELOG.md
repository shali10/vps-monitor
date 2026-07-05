# Changelog

All notable changes to this project are documented here.

## v4.2.0 - 2026-07-06

### Added

- Added project badges, table of contents, source matrix, and OSS maturity scorecard to README.
- Added `Makefile` with install, syntax, test, check, dry-run, and clean commands.
- Added `SECURITY.md` with supported versions, reporting guidance, and sensitive-data boundaries.
- Added GitHub Issue templates for bug reports and feature requests.
- Added Dependabot configuration for pip and GitHub Actions.
- Added per-source documentation under `docs/sites/` for `czl` and `dujiaojing`.
- Added examples: `examples/minimal-czl.json` and `examples/offer.example.json`.

### Changed

- Bumped package version to `4.2.0`.
- Expanded README from a working public README into a more complete OSS project homepage.
- Tightened public placeholder examples so they do not resemble real tokens.

## v4.1.0 - 2026-07-06

### Added

- Added Chinese public README with quick start, command table, systemd notes, security boundary, and source-adapter guide.
- Added MIT `LICENSE`.
- Added `pyproject.toml` with package metadata and `vpsmon-v4` console script.
- Added `.env.example` for Telegram and source tokens.
- Added documentation under `docs/`: installation, configuration, architecture, pitfalls, contributing, and release checklist.
- Added GitHub Actions workflow for Python 3.10-3.12 tests.
- Added package version `vpsmon.__version__ = "4.1.0"`.

### Changed

- Removed checked-in `config.json` and `config.production.json`; public repositories should only track `config.example.json`.
- Expanded `.gitignore` to exclude local config, build outputs, coverage files, and package metadata.
- Reframed the project as a public OSS tool instead of an internal production snapshot.

## v4.0.0 - 2026-07-05

### Added

- Reworked monitor into a typed package with source adapters, normalized offer models, SQLite state, and shared Telegram formatting.
- Added built-in adapters for `dujiaojing` and `czl`.
- Added event diffing so first-run behavior, restock detection, and sold-out updates are handled consistently.
- Added source-specific filtering and pool rules.
- Added systemd timer examples for periodic checks.
- Added tests for parsing, filtering, message rendering, summary rendering, and Telegram send plumbing.

### Changed

- Replaced single-script state handling with SQLite-backed state storage.
- Standardized Telegram output across sources.
