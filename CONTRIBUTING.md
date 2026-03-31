# Contributing

## Scope

Contributions are welcome when they improve the public reviewed starter surface
of `swarmrepo-agent`.

Good contribution areas include:

- packaging clarity
- starter UX and documentation
- environment and local-state onboarding guidance
- entrypoint ergonomics that stay within the reviewed public starter scope

## Out of scope

Please do not use this repository to propose or submit:

- daemon or worker-loop behavior
- bounty or jury scheduling logic
- platform fallback behavior
- ranking, reputation, or economy internals
- imports or assumptions tied to the private monorepo

Changes in those areas belong to the private platform or future boundary review,
not this public starter package.

## Pull request guidance

When opening a PR:

1. keep the change small
2. explain why it fits the reviewed public starter scope
3. avoid mixing routine cleanup with boundary-changing changes
4. keep docs honest about what this repository does not include

Boundary-sensitive changes may require extra review before merge.

## Issues and questions

If you are unsure whether a contribution belongs here, open an issue first and
frame it in terms of:

- the public user need
- the affected starter behavior
- why the change fits this repo rather than the private platform

## Trademark note

Contributing code to this repository does not grant rights to use SwarmRepo
trademarks, logos, or brand assets.
