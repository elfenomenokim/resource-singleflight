# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-19

### Added

- `ResourceCoordinator` runs at most one worker per key and gives every caller the same joinable `Future`.
- Cached results use a per-key monotonic TTL through `submit(..., cache_ttl=...)`.
- `force=True` replaces the current generation; the superseded `Future` is resolved from the replacement
  so no caller hangs, and the replaced worker cannot publish or cache its result.
- `invalidate(key)` and `clear()` drop cached values, retiring joinable flights while retaining ownership
  of workers already running.
- `wait_for_idle(timeout=None)` reports when every worker the coordinator started has exited.
- `env_flag(names, *, default=True)` reads a boolean switch from the first environment variable that is
  set, treating anything outside `0/false/no/off` as enabled.
- The worker thread name comes from `thread_name_prefix=`, so a program labels its own threads.

[Unreleased]: https://github.com/elfenomenokim/resource-singleflight/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/elfenomenokim/resource-singleflight/releases/tag/v0.1.0
