# R11 model routing and acceptance

R11 keeps the user-selected coordinator. Routine reading and reversible execution use low-cost roles; complex analysis and implementation use Sol roles. Use scripts for parseable tasks; cross-file scope or file count alone does not trigger escalation.

| Role | Model / effort | Configured sandbox |
| --- | --- | --- |
| luna_explorer | gpt-6-luna / low | read-only |
| luna_batch_worker | gpt-6-luna / low | read-only |
| luna_worker | gpt-6-luna / medium | workspace-write |
| terra_explorer | gpt-6.1-sol / medium | read-only |
| terra_worker | gpt-6.1-sol / medium | workspace-write |
| sol_specialist | gpt-6.1-sol / high | read-only |

The default child model is GPT-6 Luna / low. Merge only these configuration keys while preserving the existing root model, provider, identity, and personal rules. Examples and profiles are deployment candidates; register roles using the current host's supported mechanism.

## Verify actual adoption separately

Record requested model/effort, host registration, configured profile, and actual child turn_context separately. Fixed roles may ignore overrides; updated files do not prove that an old session reloaded the mapping. First use a read-only task to verify parent/child identity, role, model, and effort. Stop mismatches and return to the coordinator rather than impersonating the target with generic roles.

Until new Luna roles are registered, the existing luna_batch_worker handles only frozen batches and necessary read-only checks on their output. Ordinary retrieval, commands, tests, and writes remain with the coordinator. Automatic model-unavailability fallback uses only registered Terra roles whose mapping matches the target. Before writer handoff, verify termination, read back artifacts, and increment epoch. Changing models cannot hide acceptance failures.

The bundled [Skill](../skills/design-evidence-led-agent-workflow/SKILL.md) provides scripts/validate_agent_route.py. It reads one explicit profile and one explicit child transcript, requiring parent/child IDs, requested model/effort, and registered model; multiple turns need an exact turn ID. Missing metadata, identity conflicts, old registration, and actual model/effort mismatches return a nonzero exit code. Configured and actual sandbox are separate fields; model agreement does not prove host-enforced isolation.

## Evidence and checks

Observed incidents include a new requested model with an old actual role model, and correct extracted fields with a wrong summary boolean. This package preserves reusable checks rather than private transcripts or account records. Tests use synthetic positive/negative examples and do not prove runtime adoption on other machines.

Recompute parseable fields, counts, and booleans with scripts. A worker's matches_expected, pass, or null field is not acceptance evidence. This release does not claim runtime acceptance for every new role or proven cost savings.

## Authorization boundary

R11 does not reopen the Spark provider, disabled aliases, Hooks, or recovery paths. The original public R10 Astra root eligibility remains gpt-5.6-sol; its scripts, documentation, and one-shot authorization ledger are unchanged. Moving ordinary roles to 6.1 does not expand this channel. Installing a Skill, editing configuration, or publishing the repository never authorizes an Astra call.

[中文](model-routing-r11.md)
