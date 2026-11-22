import threading

import pytest

from resource_singleflight import ResourceCoordinator, env_flag


def gate():
    started, release = threading.Event(), threading.Event()
    return started, release


def test_callers_of_one_key_share_one_worker():
    coordinator = ResourceCoordinator()
    started, release = gate()
    calls = []

    def work():
        calls.append(1)
        started.set()
        release.wait(5)
        return "value"

    first = coordinator.submit("key", work)
    assert started.wait(2)
    second = coordinator.submit("key", work)
    release.set()
    assert first is second
    assert first.result(2) == "value"
    assert calls == [1]
    assert coordinator.wait_for_idle(2)


def test_cache_ttl_serves_the_result_without_rerunning():
    coordinator = ResourceCoordinator()
    calls = []

    def work():
        calls.append(1)
        return len(calls)

    assert coordinator.submit("key", work, cache_ttl=30).result(2) == 1
    coordinator.wait_for_idle(2)
    assert coordinator.submit("key", work, cache_ttl=30).result(2) == 1
    assert calls == [1]


def test_no_ttl_reruns_after_completion():
    coordinator = ResourceCoordinator()
    calls = []

    def work():
        calls.append(1)
        return len(calls)

    assert coordinator.submit("key", work).result(2) == 1
    coordinator.wait_for_idle(2)
    assert coordinator.submit("key", work).result(2) == 2


def test_force_supersedes_and_the_old_future_gets_the_new_result():
    coordinator = ResourceCoordinator()
    started, release = gate()

    def stale():
        started.set()
        release.wait(5)
        return "stale"

    old = coordinator.submit("key", stale, cache_ttl=30)
    assert started.wait(2)
    new = coordinator.submit("key", lambda: "fresh", cache_ttl=30, force=True)
    assert new is not old
    assert new.result(2) == "fresh"
    assert old.result(2) == "fresh"
    release.set()
    assert coordinator.wait_for_idle(2)
    # The superseded worker finished last but must not overwrite the cache.
    assert coordinator.submit("key", lambda: "other", cache_ttl=30).result(2) == "fresh"


def test_invalidate_makes_the_next_submit_rerun():
    coordinator = ResourceCoordinator()
    calls = []

    def work():
        calls.append(1)
        return len(calls)

    coordinator.submit("key", work, cache_ttl=30).result(2)
    coordinator.wait_for_idle(2)
    coordinator.invalidate("key")
    assert coordinator.submit("key", work, cache_ttl=30).result(2) == 2


def test_an_exception_reaches_every_caller_and_is_not_cached():
    coordinator = ResourceCoordinator()
    calls = []

    def work():
        calls.append(1)
        raise ValueError("boom")

    future = coordinator.submit("key", work, cache_ttl=30)
    with pytest.raises(ValueError):
        future.result(2)
    coordinator.wait_for_idle(2)
    with pytest.raises(ValueError):
        coordinator.submit("key", work, cache_ttl=30).result(2)
    assert calls == [1, 1]


def test_clear_cancels_flights_and_drops_the_cache():
    coordinator = ResourceCoordinator()
    started, release = gate()

    def work():
        started.set()
        release.wait(5)
        return "late"

    future = coordinator.submit("key", work, cache_ttl=30)
    assert started.wait(2)
    coordinator.clear()
    assert future.cancelled()
    release.set()
    assert coordinator.wait_for_idle(2)
    assert coordinator.submit("key", lambda: "new", cache_ttl=30).result(2) == "new"


def test_env_flag(monkeypatch):
    monkeypatch.delenv("RSF_A", raising=False)
    monkeypatch.delenv("RSF_B", raising=False)
    assert env_flag("RSF_A") is True
    assert env_flag("RSF_A", default=False) is False
    monkeypatch.setenv("RSF_B", " Off ")
    assert env_flag(["RSF_A", "RSF_B"]) is False
    monkeypatch.setenv("RSF_A", "typo")
    assert env_flag(["RSF_A", "RSF_B"]) is True
