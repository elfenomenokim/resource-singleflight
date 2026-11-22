#!/usr/bin/env python3
"""Measure one-work-per-key coalescing and cached-submit cost; rewrite coalesce.json.

Run from the repository root: python3 docs/bench/coalesce.py
"""
import importlib.util
import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module():
    path = ROOT / "src/resource_singleflight/core.py"
    spec = importlib.util.spec_from_file_location("rsf", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def coalesce(core, callers=50):
    """Return (work calls, elapsed ms) for `callers` threads asking for one key."""
    coordinator = core.ResourceCoordinator(thread_name_prefix="bench")
    started, release = threading.Event(), threading.Event()
    calls = []

    def work():
        calls.append(1)
        started.set()
        release.wait(5)
        return "value"

    futures = [None] * callers
    begin = time.perf_counter()
    threads = [threading.Thread(target=lambda i=i: futures.__setitem__(
        i, coordinator.submit("key", work, cache_ttl=30.0))) for i in range(callers)]
    for thread in threads:
        thread.start()
    started.wait(5)
    release.set()
    for thread in threads:
        thread.join(5)
    elapsed = (time.perf_counter() - begin) * 1000
    assert {future.result(1) for future in futures} == {"value"}
    return len(calls), elapsed


def cached(core, submits=1000):
    coordinator = core.ResourceCoordinator(thread_name_prefix="bench")
    coordinator.submit("key", lambda: "value", cache_ttl=60.0).result(1)
    begin = time.perf_counter()
    for _ in range(submits):
        coordinator.submit("key", lambda: "value", cache_ttl=60.0).result(1)
    return (time.perf_counter() - begin) / submits * 1e6


def main():
    core = module()
    work_calls, elapsed = coalesce(core)
    data = {
        "schema": "resource-singleflight-bench/1",
        "date": time.strftime("%Y-%m-%d"),
        "host": "macOS arm64 (Apple M5 Pro)",
        "python": ".".join(map(str, __import__("sys").version_info[:3])),
        "concurrent_callers": 50,
        "work_calls_for_50_callers": work_calls,
        "coalesce_elapsed_ms": round(elapsed, 1),
        "cached_submit_us": round(cached(core), 1),
    }
    (ROOT / "docs/bench/coalesce.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
