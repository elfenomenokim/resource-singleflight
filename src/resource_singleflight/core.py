"""Process-wide duplicate-work suppression for refreshable resources.

One `ResourceCoordinator` runs at most one worker per key, hands every caller the
same joinable `Future`, caches a result for a caller-chosen TTL, and supersedes a
worker by generation so a detached read cannot publish a value its caller already
replaced. The module depends on the standard library only.

Configuration is by argument: `thread_name_prefix` names the workers, and
`env_flag` reads the caller's own rollback switch. A program that wants one shared
coordinator creates one; nothing here requires a module-level singleton.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future, InvalidStateError
from typing import Any, Callable, Hashable, Sequence


class ResourceCoordinator:
    """Own worker lifetimes while exposing one joinable Future per resource key."""

    # Bumped whenever a key is invalidated. A read carries the generation it
    # started under and refuses to write its result if that generation is no
    # longer current, so a detached read cannot resurrect a value the caller
    # already replaced.
    def __init__(self, *, thread_name_prefix: str = "singleflight") -> None:
        if not isinstance(thread_name_prefix, str) or not thread_name_prefix:
            raise ValueError("thread_name_prefix must be a non-empty string")
        self._thread_name_prefix = thread_name_prefix
        # Publication invokes Future callbacks synchronously. An RLock keeps the
        # generation decision and publication atomic while allowing our forwarding
        # callback chain to resolve superseded Futures in the same thread.
        self._lock = threading.RLock()
        self._flights: dict[Hashable, Future] = {}
        # `_flights` names only the generation new callers may join. Superseding
        # that generation must not discard ownership of the worker that is still
        # executing, so every started thread remains here until its `finally`.
        self._workers: dict[Future, threading.Thread] = {}
        self._cache: dict[Hashable, tuple[float, Any]] = {}
        self._generation: dict[Hashable, int] = {}

    @staticmethod
    def _forward_replacement(replacement: Future, superseded: Future) -> None:
        """Resolve an issued Future from the work that replaced its generation."""
        if replacement.cancelled():
            superseded.cancel()
            return
        try:
            result = replacement.result()
        except BaseException as exc:
            try:
                superseded.set_exception(exc)
            except InvalidStateError:
                pass
        else:
            try:
                superseded.set_result(result)
            except InvalidStateError:
                pass

    def submit(
        self,
        key: Hashable,
        function: Callable[[], Any],
        *,
        cache_ttl: float = 0.0,
        force: bool = False,
    ) -> Future:
        with self._lock:
            existing = self._flights.get(key)
            # A forced submit must not join an in-flight fetch: start a fresh
            # future and replace the stored flight so later non-force submits
            # join the new one. The stale flight keeps running, but its teardown
            # identity check (`is future`) stops it from popping the new future.
            if existing is not None and not force:
                return existing
            if not force:
                cached = self._cache.get(key)
                if cached is not None:
                    expires_at, result = cached
                    if time.monotonic() < expires_at:
                        ready = Future()
                        ready.set_result(result)
                        return ready
                    self._cache.pop(key, None)

            if force:
                # A forced read replaces the one in flight. Without bumping the
                # generation both shared one, so whichever finished LAST won the
                # cache - and that could be the read the caller replaced.
                self._cache.pop(key, None)
                self._generation[key] = self._generation.get(key, 0) + 1
            future = Future()
            if force and existing is not None and not existing.done():
                # The old function cannot be stopped safely, and its result must
                # not escape. Keep its already-issued promise useful by resolving
                # it from the replacement generation instead of cancelling it.
                future.add_done_callback(
                    lambda replacement, superseded=existing: self._forward_replacement(
                        replacement,
                        superseded,
                    )
                )
            self._flights[key] = future
            generation = self._generation.get(key, 0)

            def execute() -> None:
                try:
                    result = function()
                except BaseException as exc:
                    with self._lock:
                        current = (
                            self._generation.get(key, 0) == generation
                            and self._flights.get(key) is future
                            and not future.cancelled()
                        )
                        if current:
                            try:
                                # Publish before releasing the same lock used by
                                # force. A replacement can therefore happen only
                                # wholly before this exception or wholly after it.
                                future.set_exception(exc)
                            except InvalidStateError:
                                pass
                            if self._flights.get(key) is future:
                                self._flights.pop(key, None)
                else:
                    with self._lock:
                        # Result publication and cache ownership share one
                        # generation decision. A superseded worker may finish, but
                        # it cannot resolve its reattached Future or repopulate cache.
                        current = (
                            self._generation.get(key, 0) == generation
                            and self._flights.get(key) is future
                            and not future.cancelled()
                        )
                        if current:
                            if cache_ttl > 0:
                                self._cache[key] = (
                                    time.monotonic() + float(cache_ttl),
                                    result,
                                )
                            try:
                                # The current-generation check and publication
                                # are one atomic coordinator action. If force won
                                # first, this branch is skipped and the replacement
                                # callback supplies FRESH to this issued Future.
                                future.set_result(result)
                            except InvalidStateError:
                                pass
                            if self._flights.get(key) is future:
                                self._flights.pop(key, None)
                finally:
                    with self._lock:
                        if self._flights.get(key) is future:
                            self._flights.pop(key, None)
                        self._workers.pop(future, None)

            worker = threading.Thread(
                target=execute,
                name=f"{self._thread_name_prefix}-{str(key)[:48]}",
                daemon=True,
            )
            self._workers[future] = worker
            # Start while ownership is locked in. `invalidate`, `force`, `clear`,
            # and `wait_for_idle` can never observe an unstarted tracked worker or
            # a started untracked one.
            worker.start()
        return future

    def invalidate(self, key: Hashable) -> None:
        """Drop one cached result so the next submit re-runs its work.

        Needed after an out-of-band refresh: the Qwen browser fetch can finish
        inside the 2s provider TTL, and the recollection that follows would
        otherwise be served the pre-fetch snapshot and show the same stale card.
        """
        with self._lock:
            self._cache.pop(key, None)
            # Dropping only the cached value let a read that began during an
            # out-of-band refresh stay joinable; the next submit joined it and
            # replayed pre-refresh data. Retire the joinable flight so a fresh read
            # starts, while `_workers` retains ownership until the old work exits.
            flight = self._flights.pop(key, None)
            if flight is not None:
                flight.cancel()
            self._generation[key] = self._generation.get(key, 0) + 1

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            # Resetting generations to zero made an already-detached gen-0 read
            # current again, so it could write after clear(). Bump instead.
            for key in set(self._generation) | set(self._flights):
                self._generation[key] = self._generation.get(key, 0) + 1
            for future in self._flights.values():
                future.cancel()
            self._flights.clear()

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """Wait until every worker owned by this coordinator has exited.

        Supersession redirects the public Future, while invalidate/clear cancel it;
        none can stop arbitrary Python code already inside a syscall. Those workers
        remain owned and observable here until their bounded work returns.
        """
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while True:
            with self._lock:
                workers = list(self._workers.values())
            if not workers:
                return True
            for worker in workers:
                remaining = None
                if deadline is not None:
                    remaining = max(0.0, deadline - time.monotonic())
                    if remaining == 0:
                        return False
                worker.join(timeout=remaining)
            if deadline is not None and time.monotonic() >= deadline:
                with self._lock:
                    return not self._workers


FALSE_WORDS = frozenset({"0", "false", "no", "off"})


def env_flag(names: str | Sequence[str], *, default: bool = True) -> bool:
    """Read a boolean switch from the first of `names` that is set.

    Unset keeps `default`. Any value outside the false words keeps it enabled, so a
    typo never silently disables coordination.
    """

    candidates = (names,) if isinstance(names, str) else names
    for name in candidates:
        value = os.environ.get(name)
        if value is not None:
            return value.strip().lower() not in FALSE_WORDS
    return default
