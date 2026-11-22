# Contributing to resource-singleflight

Bug reports and patches are welcome. You do not need to ask before opening a pull request for a bug fix.

## Before you start

- **A caller hung, or got a stale value:** open an issue with the submission order, the `force` and
  `invalidate` calls, and what each caller received. A small blocking-work script that reproduces it is
  the most useful evidence.
- **A change to when a worker may publish:** open an issue first. This is the rule the package exists for.
- **A security problem:** do not open a public issue. See [SECURITY.md](SECURITY.md).

## Set up

```sh
git clone https://github.com/elfenomenokim/resource-singleflight
cd resource-singleflight
python3 -m compileall -q src
python3 docs/bench/coalesce.py
```

Run the tests with `python3 -m pip install . pytest && python3 -m pytest -q tests`. Make the concurrent
window deterministic by blocking the work function on a `threading.Event`, then release it — never rely
on `sleep` to order threads.

## Rules a patch must keep

- A worker publishes only when its generation is current, its `Future` is the stored flight, and that
  `Future` is not cancelled. All three, together.
- Cache writes and the generation decision happen under one lock.
- A replaced worker's callers are resolved from the replacement. Never leave them cancelled.
- `_workers` owns every started thread until it exits; `wait_for_idle` reports on that set.
- User code is never called while the lock is held.
- Keep `ResourceCoordinator` free of module-level state, so two instances do not interfere.

## What a good patch has

- **A script** that shows the wrong behaviour before the change and the right behaviour after it.
- **A line under Unreleased** in [CHANGELOG.md](CHANGELOG.md) when a caller will notice.
- **The platforms you did not test** written in the pull request. CI covers Linux, macOS and Windows.

## Licence

Contributions are licensed under the MIT licence in [LICENSE](LICENSE).
