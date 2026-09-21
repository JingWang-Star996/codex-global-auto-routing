[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$hook = Join-Path $root 'hooks\spark-router-circuit.ps1'
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('router-retired-provider-' + [guid]::NewGuid().ToString('N'))
$statePath = Join-Path $temporaryRoot 'model-router-v4.json'
$sessionsRoot = Join-Path $temporaryRoot 'sessions'
$script:passed = 0

function Check {
    param([bool]$Ok, [string]$Name)
    if (-not $Ok) { throw "FAIL $Name" }
    $script:passed++
    "PASS $Name"
}

function Invoke-Hook {
    param([object]$Event, [string]$ExpectedEvent)
    $json = $Event | ConvertTo-Json -Depth 20 -Compress
    $output = @($json | & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $hook -StatePath $statePath -SessionsRoot $sessionsRoot -ExpectedEvent $ExpectedEvent 2>&1)
    if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
    return (($output -join "`n") | ConvertFrom-Json)
}

function New-PreToolEvent {
    param([string]$AgentType, [string]$Policy)
    return [ordered]@{
        hook_event_name = 'PreToolUse'
        session_id = 'retired-provider-test'
        turn_id = [guid]::NewGuid().ToString('N')
        tool_name = 'spawn_agent'
        tool_input = [ordered]@{
            agent_type = $AgentType
            task_name = 'retired_provider_test'
            fork_turns = 'none'
            model = 'caller-supplied-model-must-be-removed'
            reasoning_effort = 'low'
            message = "work_unit_id: retired-provider-test`nfallback_policy: $Policy`nread only"
        }
    }
}

function New-LegacyState {
    param([object]$Model)
    return [pscustomobject][ordered]@{
        schema_version = 4
        model = $Model
        circuit_state = 'closed'
        generation = 0
        failure_kind = $null
        failure_count = 0
        opened_at = $null
        last_observed_at = $null
        next_probe_at = $null
        last_source = 'retired_provider_test'
        evidence_sha256 = $null
        last_failure_fingerprint = $null
        probe_lease_id = $null
        probe_generation = $null
        probe_session_id = $null
        probe_turn_id = $null
        probe_work_unit_id = $null
        probe_agent_type = $null
        probe_agent_id = $null
        probe_started_at = $null
        probe_lease_until = $null
    }
}

try {
    [IO.Directory]::CreateDirectory($sessionsRoot) | Out-Null
    $legacyModel = 'gpt-' + '5.3' + '-codex-spark'
    $activeSources = @(
        (Join-Path $root 'AGENTS.example.md'),
        (Join-Path $root 'README.md'),
        (Join-Path $root 'README.en.md'),
        (Join-Path $root 'config.example.toml'),
        (Join-Path $root 'hooks.example.json'),
        $hook
    ) + @(
        Get-ChildItem -LiteralPath (Join-Path $root 'agents'), (Join-Path $root 'docs'), (Join-Path $root 'scripts'), (Join-Path $root 'i18n\en') -File -Recurse |
            Select-Object -ExpandProperty FullName
    )
    $legacyHits = @(Select-String -LiteralPath $activeSources -SimpleMatch $legacyModel -CaseSensitive:$false)
    Check ($legacyHits.Count -eq 0) 'active public sources contain no retired concrete model binding'

    $hookText = Get-Content -Raw -LiteralPath $hook -Encoding UTF8
    Check ($hookText.Contains('$script:SparkProviderRetired = $true')) 'retirement flag is script-owned and enabled'

    $definitionEnd = $hookText.IndexOf('$parsedEvent = $null', [StringComparison]::Ordinal)
    if ($definitionEnd -lt 0) { throw 'Hook definition boundary not found' }
    . ([scriptblock]::Create($hookText.Substring(0, $definitionEnd))) -StatePath $statePath -SessionsRoot $sessionsRoot
    Check (Test-StateInvariant (New-LegacyState 'legacy-provider-state')) 'legacy non-empty string state remains compatible'
    foreach ($invalidModel in @($true, 123, [pscustomobject]@{x=1}, '   ', $null)) {
        Check (-not (Test-StateInvariant (New-LegacyState $invalidModel))) 'non-string or blank state model is rejected'
    }

    $automaticExplorer = Invoke-Hook (New-PreToolEvent 'spark_explorer' 'automatic') 'PreToolUse'
    Check ($automaticExplorer.hookSpecificOutput.updatedInput.agent_type -eq 'terra_explorer') 'automatic explorer alias routes to Terra'
    Check ($null -eq $automaticExplorer.hookSpecificOutput.updatedInput.PSObject.Properties['model']) 'automatic route removes caller model override'
    Check ([string]$automaticExplorer.hookSpecificOutput.updatedInput.message -match 'router_v4_reason: spark_provider_retired') 'automatic route records retired-provider reason'

    $automaticWorker = Invoke-Hook (New-PreToolEvent 'spark_patch_worker' 'automatic') 'PreToolUse'
    Check ($automaticWorker.hookSpecificOutput.updatedInput.agent_type -eq 'terra_worker') 'automatic patch alias routes to Terra worker'

    $pinned = Invoke-Hook (New-PreToolEvent 'spark_explorer' 'pinned') 'PreToolUse'
    Check ($pinned.hookSpecificOutput.permissionDecision -eq 'deny') 'pinned alias is denied'
    Check ($pinned.hookSpecificOutput.permissionDecisionReason -eq 'spark_router_retired_provider') 'pinned denial reports retired provider'

    $quota = [ordered]@{
        hook_event_name = 'PostToolUse'
        session_id = 'retired-provider-test'
        turn_id = 'quota'
        tool_name = 'spawn_agent'
        tool_response = [ordered]@{error = [ordered]@{codex_error_info = 'usage_limit_exceeded'; message = 'usage limit for retired provider'}}
    }
    $quotaResponse = Invoke-Hook $quota 'PostToolUse'
    Check (@($quotaResponse.PSObject.Properties).Count -eq 0) 'historical quota evidence produces no action'
    Check (-not (Test-Path -LiteralPath $statePath)) 'historical quota evidence cannot create or mutate circuit state'

    $legacyState = New-LegacyState 'legacy-provider-state'
    $legacyState | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $statePath -Encoding UTF8
    $stateBefore = [IO.File]::ReadAllBytes($statePath)
    $transcriptPath = Join-Path $sessionsRoot 'retired-provider-transcript.jsonl'
    $transcriptRecord = [ordered]@{
        type = 'event_msg'
        payload = [ordered]@{
            type = 'task_complete'
            error = [ordered]@{codex_error_info = 'usage_limit_exceeded'; message = 'usage limit for retired provider'}
        }
    }
    $transcriptRecord | ConvertTo-Json -Depth 20 -Compress | Set-Content -LiteralPath $transcriptPath -Encoding UTF8
    $stop = Invoke-Hook ([ordered]@{
        hook_event_name = 'SubagentStop'
        session_id = 'retired-provider-test'
        turn_id = 'transcript-quota'
        agent_type = 'spark_explorer'
        agent_id = 'retired-provider-agent'
        agent_transcript_path = $transcriptPath
    }) 'SubagentStop'
    $stateAfter = [IO.File]::ReadAllBytes($statePath)
    Check (@($stop.PSObject.Properties).Count -eq 0) 'historical transcript quota evidence produces no action'
    Check ([Convert]::ToBase64String($stateBefore) -ceq [Convert]::ToBase64String($stateAfter)) 'historical transcript quota evidence leaves legacy state unchanged'

    $session = Invoke-Hook ([ordered]@{hook_event_name='SessionStart';session_id='retired-provider-test'}) 'SessionStart'
    Check ($session.hookSpecificOutput.additionalContext -match 'former provider is retired') 'SessionStart reports retirement boundary'

    "PASSED=$script:passed"
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force }
}
