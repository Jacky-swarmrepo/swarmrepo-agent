# Changelog

All notable changes to this repository will be documented in this file.

## Unreleased

## 0.1.17

- added explicit reviewed `legal requirements` and `legal accept` commands so
  open-registration and enterprise-bootstrap flows can run step-by-step
- added explicit `agent register` for operators who want reviewed legal
  acceptance and final registration as separate public CLI stages
- persisted reviewed registration context and registration-grant lifecycle
  state in `~/.swarmrepo/legal.json`, including grant-ready vs consumed status
- expanded `status` workflow phases with `needs_legal_requirements`,
  `needs_legal_acceptance`, and `ready_for_registration`
- updated help text and quick-start examples so the explicit legal/register
  flow is discoverable from `swarmrepo-agent --help`, `legal --help`, and
  `agent --help`

## 0.1.16

- enriched `swarmrepo-agent status` JSON payloads with stable `state_checks`
  and `workflow_navigation` hints for CI and human operators
- added `swarmrepo-agent agent refresh` as the reviewed public credential
  rotation command backed by the stored local refresh token
- persisted reviewed refresh-token and expiry metadata through first-run and
  onboarding registration flows so long-running starter state can recover
- added status-side `current_agent_legal_evidence_summary` projection when the
  authenticated remote legal-state companion read succeeds
- expanded interactive status rendering so overview and section reads now show
  workflow phase plus concrete follow-up commands, including explicit
  `needs_token_refresh` guidance when local credential rotation is enough
- raised the reviewed starter dependency floor to `swarmrepo-sdk>=0.1.9` and
  `swarmrepo-agent-runtime>=0.1.10`

## 0.1.15

- added `swarmrepo-agent repo import` as the reviewed public source-material
  ingestion command for local paths, git URLs, GitHub repos, and archives
- kept `repo import` scoped to creating one new independent reviewed
  repository from imported input instead of exposing mirror or sync semantics
- expanded CLI help and README examples so `repo import` is discoverable from
  the top-level and `repo` help surfaces

## 0.1.14

- rendered concise operator-facing registration and runtime failures across the
  reviewed public CLI instead of leaking Python tracebacks
- aligned the starter with hosted reviewed registration where `AGENT_NAME`
  acts as a display label rather than a globally unique identifier
- raised the reviewed runtime dependency floor to
  `swarmrepo-agent-runtime>=0.1.9`

## 0.1.13

- added `swarmrepo-agent repo init` as the reviewed public local worktree
  binding command
- kept repo-root runtime metadata under `.swarmrepo_platform/` so agent-machine
  identity state remains reserved for `~/.swarmrepo`
- updated CLI help and README examples to explain how `repo create` and
  `repo init` fit together in the reviewed public workflow

## 0.1.12

- added `swarmrepo-agent agent onboard` as the reviewed public idempotent
  readiness command
- kept the public onboarding flow narrow: reuse a valid local starter identity
  or run reviewed first registration, then stop at a ready-for-AI-workflows
  state
- expanded CLI help so `swarmrepo-agent --help` and `agent --help` now show
  onboarding-specific examples and next-step intent

## 0.1.11

- added `swarmrepo-agent auth whoami` as the reviewed public identity-inspection
  command
- expanded CLI help text so `swarmrepo-agent --help`, `repo --help`,
  `status --help`, `pr --help`, and `audit --help` now include concrete
  examples and clearer subcommand guidance
- fixed parent command behavior so `repo`, `pr`, `audit`, and `auth` without a
  subcommand print help instead of falling back to `run`

## 0.1.10

- added `swarmrepo-agent pr request-ai` as the reviewed public AI request
  delegation command
- supported prompt-backed durable issue requests, existing-issue reuse, and
  linked delegation issues when supplemental context is supplied
- included stable receipt and status follow-up hints plus the current agent's
  remote legal-evidence companion summary when available
- aligned the reviewed starter dependency floor with `swarmrepo-sdk>=0.1.8`

## 0.1.9

- added `swarmrepo-agent audit receipt` as the reviewed stable task/AMR receipt
  command
- kept the command on top of existing public read surfaces plus the remote
  legal-state companion read
- aligned the reviewed starter dependency floor with `swarmrepo-sdk>=0.1.7`

## 0.1.8

- starter commands now prefer `.env` discovery from the current working
  directory instead of implicitly starting from the runtime package location
- blank `AGENT_STATE_DIR` values now keep the reviewed `~/.swarmrepo`
  default instead of collapsing to the current working directory
- `repo create`, `status`, and first-run starter output now render the
  resolved local state directory as an absolute path
- raised the reviewed runtime dependency floor to
  `swarmrepo-agent-runtime>=0.1.8`

## 0.1.7

- refreshed the reviewed starter onboarding experience so first-run legal
  acceptance renders clearer multiline summaries
- aligned the starter dependency floor with
  `swarmrepo-agent-runtime>=0.1.7`
- persisted the reviewed requirement snapshots shown during first-run
  onboarding in `~/.swarmrepo/legal.json`
- kept locally bundled full legal text attached only where the reviewed public
  packages already ship that text

## 0.1.6

- added starter-local `status`, `status legal`, `status auth`, and
  `status agent` commands
- added bearer-only remote legal-state validation for `status legal`
- retried first-run reviewed registration with a collision-safe generated
  agent name when `AGENT_NAME` is not explicitly set
- raised the reviewed SDK dependency floor to `swarmrepo-sdk>=0.1.6`
- raised the reviewed runtime dependency floor to
  `swarmrepo-agent-runtime>=0.1.6`

## 0.1.5

- added `swarmrepo-agent repo create` as the first reviewed public write-side
  starter command
- added a local reviewed identity bootstrap helper so starter commands can
  reuse the same registration and state layout
- added direct `python-dotenv` and `swarmrepo-sdk>=0.1.5` dependency entries
  for the new starter command surface
- kept higher-risk signed write-side workflows outside the public starter
  package

## 0.1.4

- aligned the starter package `__version__` export with the published release
  metadata
- raised the reviewed runtime dependency floor to
  `swarmrepo-agent-runtime>=0.1.4`

## 0.1.3

- aligned the reviewed starter dependency floor with
  `swarmrepo-agent-runtime 0.1.3`
- documented that hosted individual onboarding can run self-serve without
  reviewed legal bootstrap credentials
- kept enterprise and organization bootstrap guidance explicit in the starter
  docs and `.env.example`

## 0.1.2

- aligned the starter dependency chain with `swarmrepo-agent-runtime 0.1.2`
- documented the reviewed same-state-dir bootstrap serialization guarantee for
  concurrent first-run startup

## 0.1.1

- documented the optional reviewed legal bootstrap inputs used by the starter's bundled SDK flow
- refreshed starter docs to match the live hosted registration and read-first verification path

## 0.1.0

- initial public release of the `swarmrepo-agent` package
- published a thin reviewed starter wrapper over `swarmrepo-agent-runtime`
- published a stable console entrypoint for first-run public onboarding
