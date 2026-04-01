# Changelog

All notable changes to this repository will be documented in this file.

## Unreleased

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
