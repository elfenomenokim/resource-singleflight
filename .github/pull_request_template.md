## What and why

<!-- One paragraph. Link the issue when there is one. -->

## How to check it

<!-- The blocking script and the command a reviewer runs. -->

## Checklist

- [ ] The change is exercised with a work function blocked on an `Event`, not on `sleep`.
- [ ] The generation rule still holds: current generation, stored flight, not cancelled.
- [ ] A line is added under Unreleased in CHANGELOG.md when a caller will notice.
- [ ] README.md and README.ko.md still describe the behaviour.
- [ ] Platforms not tested are named here.
