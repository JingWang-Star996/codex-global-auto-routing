# Codex Global Multi-Model Routing · R10

[中文](README.md) | [English](README.en.md)

[![Offline tests](https://github.com/JingWang-Star996/codex-global-auto-routing/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/JingWang-Star996/codex-global-auto-routing/actions/workflows/offline-tests.yml)

An experimental, project-independent configuration package for Codex Desktop / CLI on Windows. It keeps the model selected by the user as the primary coordinator and lets that coordinator choose bounded sub-agent roles according to task shape, risk, and delegation value. It is neither a transparent main-model switch nor a host-level permission system.

## What it routes

| Work type | Route |
| --- | --- |
| Computation, precise readback, and clear low-risk edits | The coordinator uses deterministic tools directly when practical |
| Large homogeneous classification, extraction, or deduplication | `luna_batch_worker` |
| Cross-file semantic tracing and code/log inventory | `terra_explorer` |
| Routine multi-file implementation, debugging, and tests | `terra_worker` |
| Independent review of security, production configuration, or concurrency | `sol_specialist` |
| One controlled read-only assist from a Sol root after task-specific approval | `astra_specialist` |

The user-selected model remains the coordinator and owns authorization, critical verification, and the final answer. See the [English policy](i18n/en/AGENTS.example.md) for the task packet, failure, handoff, receipt, and usage rules.

Spark remains hard-disabled. The two Spark-named profiles are compatibility aliases mapped to Terra as a fail-safe; they must not be spawned and the Spark provider must not be probed. Automatic candidates go directly to Terra, and pinned Spark requests are denied. A quota reset is not restoration authorization.

## R10 controlled upward assist

Only a root task whose actual coordinator model is `gpt-5.6-sol` is eligible to request Astra. Normal work continues first. Sol asks once only when observable evidence shows bounded reasoning difficulty, an unresolved evidence conflict, or a concrete benefit from independent cross-model review. It may ask at startup if that evidence already exists. A specific pre-authorization for the current root avoids another question, but never forces a call.

Refusal, silence, and ambiguous replies are not approval. Approval may be withdrawn. A reservation already created stays consumed, and a provider call or usage already incurred cannot be promised away. Ordinary command failures, quota, login/permission blocks, and ambiguous requirements do not trigger escalation.

Each root has at most one reservation and one attempt. Astra is fixed to `gpt-6-astra/high`, performs one turn of analysis or review, and may not take over coordination, write files, delegate, or authorize actions. See the [English R10 procedure](i18n/en/docs/upward-assist-r10.md).

## Validation status and limits

- Offline regression tests cover request validation, the exclusive one-shot ledger, and spawn-message construction.
- A Sol root was observed creating an actual Astra child, but the first run was correctly rejected because its packet lacked the successful-reservation summary. Message construction was fixed; **a successful post-fix runtime analysis has not yet been validated**.
- `upward_assist.py` validates coordinator attestations and maintains a one-shot local ledger. It does not authenticate the user, root identity, or real model, and it cannot block a host call that bypasses the script.
- Hooks are observer / diagnostic only. Installation, matching hashes, trust, or Hook output do not prove host routing or enforcement.
- A profile's `read-only` sandbox is an intended setting. Actual isolation must be read from child runtime metadata; parent permissions may override it.
- Character limits are not billing-token limits. This package does not claim verified token savings or completion of a user's business outcome.

Private runtime logs, real user approvals, production ledgers, and historical deployment backups are not included. Offline tests therefore cannot replace host-runtime evidence.

## Files and setup

The Chinese source is at the repository root. A deployable English mirror is under `i18n/en/`. Scripts, Hooks, examples, and tests are language-neutral.

Use Windows PowerShell 5.1 or PowerShell 7 and Python 3.11+ (tests use the standard library only). Model and custom-role availability depend on the current host and account. Follow the documented fallback/stop rules when a model is unavailable; do not probe sideways.

1. Review the policy, profiles, and scripts, then back up the existing target configuration. Choose and fix one local `CODEX_HOME`.
2. For English deployment, merge `i18n/en/AGENTS.example.md` into the user-level `AGENTS.md` and use `i18n/en/agents/`. For Chinese, use the root equivalents. Do not mix the two language sets. Replace `<CODEX_HOME>` with the selected absolute deployment path.
3. Do not overwrite an existing `config.toml` wholesale. Register roles only through mechanisms supported by the actual host and verify that every exact role is available. Stop if a role is missing; do not impersonate it with a generic role.
4. The sole production ledger directory is `<CODEX_HOME>/state/upward-assist-r10`. Never copy test ledgers into production, switch directories, or delete a ledger to regain an attempt. Installing this package is not approval to call Astra.
5. If the optional Hook is needed, run a read-only install plan first. Review the installer separately, including any existing Hook or Token Hook hashes. The installer **manages the Hook only**; it does not deploy the policy or profiles.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-CodexRouter.ps1 -SourceRoot "$PWD" -TargetCodexHome "$env:CODEX_HOME" -PlanOnly
```

An existing `hooks.json` requires its reviewed `-ExpectedHooksSha256`. Preserving a recognized Token Hook pair also requires `-ApprovedTokenSha256`. Unknown or duplicate handlers fail closed. Omitting `-PlanOnly` performs writes; publishing this repository is not deployment approval for any machine.

After deployment, verify file digests, real child ID/model/effort/sandbox, file changes, and the target outcome as separate evidence. A new session or restart may be required. Do not treat an old session's self-report as loading proof.

## Offline validation

Run from the repository root. These commands need no API key and do not start a model or real child:

```powershell
python tests\test_upward_assist.py
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-RouterPolicyR10.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-R10AuthorizationTiming.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-BilingualParity.ps1
```

Tests use isolated fixtures and ignored output. Text invariants can detect policy drift, but cannot prove real coordinator behavior.

## Publication and license

This public repository contains portable R10 configuration and offline tests. It does not modify any deployed local configuration. See the [English changelog](CHANGELOG.en.md).

The repository is publicly readable and may be viewed and forked under GitHub's Terms of Service, but it carries no open-source license and grants no additional permission to modify or redistribute it. Never commit production state, sessions, approval references, account credentials, or machine-specific deployment evidence; ignore rules cannot erase Git history.
