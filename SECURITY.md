# Security policy

## Supported versions

Security fixes go into the latest release. Upgrade before reporting, in case the problem is
already fixed.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Older | No |

## Reporting a vulnerability

Report it privately, not in a public issue: use the
[Report a vulnerability](https://github.com/elfenomenokim/resource-singleflight/security/advisories/new)
form on the repository's Security tab.

Include the submission order, the version, and what an attacker could do with the result. You get a
reply within a few days.

## In scope

- A caller that never receives a result because a worker was replaced, cancelled or cleared.
- A stale result that is published or cached after its generation was replaced.
- A third party's ability to influence another coordinator's keys or results through shared state.
- A thread that stays alive after `wait_for_idle()` returned true.
- An environment switch that reads as enabled when the operator set it to a false word.

## Not a vulnerability

- Work that keeps running after `force=True`. It is redirected, not interrupted; that is documented.
- Only overlapping submissions coalescing. Fast work can produce several calls; the result stays correct.
- No cross-process coordination. Each process runs its own workers by design.
- Slowness under the GIL with CPU-bound work. This coordinator targets I/O-bound refreshes.

## Disclosure

Once a fix is released, the advisory is published with credit to the reporter unless they prefer
otherwise.
