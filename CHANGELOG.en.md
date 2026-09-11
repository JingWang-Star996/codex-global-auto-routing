# Changelog

[中文](CHANGELOG.md) | [English](CHANGELOG.en.md)

## R10 publication package · 2026-09-11

- Added one controlled, read-only Sol-root-to-Astra assist. It is off by default and requires specific user approval for the current root task.
- Added local request preflight, an exclusive one-shot ledger, complete spawn-message construction with a successful-reservation summary, and offline tests.
- Defined when approval is requested, how pre-authorization works, and how refusal, silence, and withdrawal are handled at each lifecycle stage.
- Replaced private deployment paths with placeholders, included self-contained tests, and excluded private governance evidence, sessions, and production state.
- Added Chinese and English READMEs, R10 procedures, policies, and all seven profiles, with static parity checks over machine fields and critical safety boundaries.
- Positive runtime validation remains incomplete: the initial actual call was rejected for a missing message field, and no second actual call was made after the message builder was fixed.

## R9 · 2026-09-11

- Preferred deterministic tools and stopped forcing delegation solely by duration or file count.
- Allowed the original writer one repair and revalidation attempt for bounded, understood, reversible implementation failures.
- Separated configured from actual receipt fields; missing runtime metadata remains `unknown`.
- Allowed the Hook installer to preserve an existing, reviewed Token Hook pair whose digest matches; the Token Hook implementation is not distributed.

## Unchanged boundaries

The user-selected coordinator does not switch. Spark remains hard-disabled with no automatic probe. Authorization for external side effects and the final completion declaration cannot be delegated. Offline tests, deployment readback, host runtime, and actual outcomes are verified separately.
