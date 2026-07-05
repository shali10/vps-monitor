# Changelog

All notable changes to this project are documented here.

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
