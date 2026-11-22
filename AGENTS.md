# AGENTS.md

## Set up for a user

Goal: the user's Python project can `import resource_singleflight` and coalesce duplicate work. This is a library, so "working" means the check below runs with the project's own interpreter. Nothing here needs the person except knowing which project.

1. Check what is present.
   - Find the project (the folder with `pyproject.toml` or `requirements.txt`); if the user did not say which, ask: "어느 프로젝트에 넣을까요? 폴더 위치를 알려주세요." Do not install into the system Python.
   - `uv --version` prints a version. If not: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then `export PATH="$HOME/.local/bin:$PATH"`.
   - The project's interpreter is Python 3.9 or newer (`.venv/bin/python --version`). No venv yet: `uv venv` in the project folder.
2. Install into the project: `uv add resource-singleflight` (uv-managed project), or `uv pip install resource-singleflight` (plain venv), or `.venv/bin/python -m pip install resource-singleflight`. It has no dependencies.
3. Prove it, with the project's interpreter (`uv run python` or `.venv/bin/python`):
   ```sh
   python - <<'PY'
   from resource_singleflight import ResourceCoordinator
   c = ResourceCoordinator()
   a = c.submit("key", lambda: "value", cache_ttl=30.0)
   b = c.submit("key", lambda: "value", cache_ttl=30.0)
   print(a is b, a.result(1))
   PY
   ```
   Success prints `True value`.
4. If it fails, in this order:
   - `externally-managed-environment` from pip: you used the system Python; use the project's venv (steps 1-2).
   - `ModuleNotFoundError: resource_singleflight`: the check ran with a different interpreter than the install; run it with the same `python`.
   - `False value`: the first call had already finished and its `cache_ttl` was not set, so the second call started a new flight. This is expected without a TTL; only calls that overlap in time or share a cached value return the same `Future`.

## Layout

- `src/resource_singleflight/core.py`: the whole library — the coordinator, its lock, and the flag reader.
- `src/resource_singleflight/__init__.py`: the public names and the version.
- `docs/bench/coalesce.py`: re-measures coalescing and cached submit, rewriting `docs/bench/coalesce.json`.
- `docs/logo.svg`: the mark used in the README.
- `public.json`: export allowlist and repository metadata.

## Commands

Run from the repository root:

```sh
python3 -m compileall -q src
python3 -c "import sys; sys.path.insert(0,'src'); from resource_singleflight import ResourceCoordinator; print(ResourceCoordinator().submit('k', lambda: 1).result(1))"
python3 docs/bench/coalesce.py
```

Tests: `python3 -m pip install . pytest && python3 -m pytest -q tests` (CI runs them on Linux, macOS and
Windows with Python 3.9 and 3.13). A new test blocks its work function on an `Event`, so the concurrent
window is deterministic; never order threads with `sleep`.

## Changes

- Keep the generation rule: a worker may publish only when its generation is current, its `Future` is
  still the stored flight, and that `Future` is not cancelled. Do not weaken any of the three.
- Publication and cache writes stay inside the same lock as the generation decision.
- A replaced worker is resolved from the replacement, never left cancelled for its callers.
- `_workers` keeps every started thread until its `finally`. Do not remove a worker from ownership early.
- Start the worker while the lock is held, so `invalidate`, `force`, `clear` and `wait_for_idle` cannot
  observe an unstarted-but-tracked or started-but-untracked worker.
- Do not add a module-level singleton. A program creates its own coordinator; a caller that wants one
  shared object makes one.
- Keep README.md, README.ko.md, the `pyproject.toml` description and `public.json` aligned.
- A local commit is not publication. Version bumps and PyPI uploads require the maintainer's instruction.

## Hard don'ts

- Do not cancel a `Future` a caller may be waiting on without resolving it from a replacement.
- Do not stop a running worker from inside the coordinator. Redirect its result instead.
- Do not hold the lock while calling user code; only publication and bookkeeping happen under it.
