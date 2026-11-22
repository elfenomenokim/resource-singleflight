<div align="center">

<img src="https://raw.githubusercontent.com/elfenomenokim/resource-singleflight/main/docs/logo.svg" width="96" height="96" alt="resource-singleflight: many callers, one worker">

# resource-singleflight

A Python library that runs at most one worker per key and hands every caller the same joinable `Future`.

[한국어](README.ko.md) · Python 3.9+

[![license](https://img.shields.io/github/license/elfenomenokim/resource-singleflight)](LICENSE)

[Install](#install) · [Quick start](#quick-start) · [Why](#why) · [Reference](#reference)

</div>

50 threads asking for the same key produced 1 work call in 4.6 ms, and a cached submit costs 3.3 µs. Both values are saved in `docs/bench/coalesce.json`.

A refresh loop has a familiar problem: ten panes wake at the same second and each starts the same expensive read. This coordinator lets the first one work and gives the other nine the same `Future` to wait on. When a read has to be replaced, the old one keeps running but cannot publish its result any more, so a slow answer never overwrites a fresh one.

Standard library only. One file, no threads of its own beyond the workers it starts.

## Install

```sh
pip install resource-singleflight
```

Python 3.9+. No dependencies. Verified on macOS arm64 with Python 3.12.

## Quick start

```python
from resource_singleflight import ResourceCoordinator

coordinator = ResourceCoordinator(thread_name_prefix="refresh")

def read_expensive() -> str:
    return "value"

first = coordinator.submit("key", read_expensive, cache_ttl=30.0)
second = coordinator.submit("key", read_expensive, cache_ttl=30.0)
print(first is second)      # True: one worker, one Future
print(first.result(1))      # 'value'
```

Ten callers, one work call. The work function blocks until every caller has asked, which is the case coalescing is for:

```python
import threading
from resource_singleflight import ResourceCoordinator

coordinator = ResourceCoordinator()
started, release = threading.Event(), threading.Event()
calls = []

def read():
    calls.append(1)
    started.set()
    release.wait(5)
    return "value"

futures = []
target = lambda: futures.append(coordinator.submit("key", read, cache_ttl=30.0))
threads = [threading.Thread(target=target) for _ in range(10)]
for thread in threads:
    thread.start()
started.wait(2)
release.set()
for thread in threads:
    thread.join(5)

print(len(calls))                       # 1
print({f.result(2) for f in futures})   # {'value'}
```

A forced refresh replaces the in-flight read, and the superseded `Future` resolves from the replacement instead of hanging:

```python
old = coordinator.submit("key", slow_read, cache_ttl=30.0)
new = coordinator.submit("key", fast_read, cache_ttl=30.0, force=True)
print(old.result(1))   # the replacement's result, not the stale one
```

## Why

Coalescing requests sounds like a lock around a dictionary. The parts that bite are the edges:

- **A detached read must not publish.** If a refresh was replaced, its result is no longer wanted. The coordinator bumps a generation when it replaces work, and a worker may only publish while its generation is current. A superseded worker that finishes late resolves nothing and caches nothing.
- **Nobody should hang.** Cancelling a `Future` someone is waiting on would raise `CancelledError` in a caller that did nothing wrong. Instead the issued `Future` is resolved from the replacement, so every caller gets an answer.
- **Work in progress stays owned.** Arbitrary Python code already inside a syscall cannot be stopped. The coordinator keeps every started worker until it exits, and `wait_for_idle()` reports when the last one is done. A shutdown can then wait instead of hoping.
- **Cache and publication agree.** The generation check and the cache write happen under the same lock, so a replacement lands either wholly before a publication or wholly after it.

## Reference

### `ResourceCoordinator(thread_name_prefix="singleflight")`

| Method | Behaviour |
| --- | --- |
| `submit(key, function, *, cache_ttl=0.0, force=False)` | Joins the in-flight `Future` for `key`, or serves a cached value, or starts one worker. `force=True` replaces the current generation. |
| `invalidate(key)` | Drops the cached value and retires the joinable flight, retaining ownership of any running worker. |
| `clear()` | Drops every cached value and cancels every joinable flight, keeping ownership of running workers. |
| `wait_for_idle(timeout=None)` | Waits until every worker this coordinator started has exited. Returns `False` on timeout. |

`key` is any hashable. `function` takes no arguments; close over what it needs.

### `env_flag(names, *, default=True)`

Reads a boolean switch from the first of `names` that is set in the environment. Unset keeps `default`. Any value outside `0`, `false`, `no`, `off` keeps it enabled, so a typo never silently disables coordination.

## Numbers

Measured on 2026-11-19 on macOS arm64 (M5 Pro), Python 3.12.8, from `docs/bench/coalesce.json`.

| What | Result |
| --- | --- |
| 50 threads submitting one key, one 20 ms work item | 1 work call, 4.6 ms total |
| Cached submit, result already available | 3.3 µs per submit |

## Limits

- One process. There is no cross-process coordination; two processes each run their own worker.
- Only overlapping submissions coalesce. If the work finishes before the next caller submits, that caller starts its own call, or is served the cache when `cache_ttl` is above zero. Ten threads submitting a 5 µs function can produce several calls; the result is still correct.
- No persistence. The cache is an in-memory dict with a monotonic deadline per key.
- A worker cannot be interrupted. `force` redirects its result; it does not stop it. Use `wait_for_idle()` when shutdown must be bounded.
- Linux and Windows have not been exercised.

## FAQ

**Why not `functools.lru_cache`?** A cache has no in-flight state, so callers of a cold key each start their own read. This type also owns replacement, which a plain cache does not express.

**Why a `Future` and not a lock plus a dict?** A lock says "wait". A `Future` carries the result, the exception and the cancellation state, and a caller can choose its own timeout.

## Contributing

Bug reports and patches are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks and the fixture each behaviour change needs.

## Licence

MIT, in [LICENSE](LICENSE).
