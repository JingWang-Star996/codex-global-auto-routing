[CmdletBinding()]
param(
    [string]$StatePath = (Join-Path $PSScriptRoot '..\state\model-router-v4.json'),
    [datetimeoffset]$Now = [datetimeoffset]::Now,
    [ValidateSet('', 'SessionStart', 'PreToolUse', 'PostToolUse', 'SubagentStart', 'SubagentStop')]
    [string]$ExpectedEvent = '',
    [string]$ExpectedScriptSha256 = '',
    [string]$HookInputJson = '',
    [string]$SessionsRoot = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\sessions'),
    [switch]$InjectWriteFailure,
    [switch]$InjectLockFailure
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:SparkModel = 'gpt-5.3-codex-spark'
$script:SparkRoles = @('spark_explorer', 'spark_patch_worker')
$script:RouterV4HostCanaryAgentType = 'router_v4_host_canary'
$script:AutomaticSparkProviderProbeEnabled = $false
$script:TranscriptTailBytes = 262144
$script:DegradedPath = $StatePath + '.degraded'

function New-EmptyResponse { return [ordered]@{} }

function New-DenyResponse {
    param([string]$Reason)
    return [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'PreToolUse'
            permissionDecision = 'deny'
            permissionDecisionReason = $Reason
        }
    }
}

function New-ContextResponse {
    param([string]$EventName, [string]$Context)
    return [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = $EventName
            additionalContext = $Context
        }
    }
}

function New-SystemMessageResponse {
    param([string]$Message)
    return [ordered]@{ systemMessage = $Message }
}

function Add-FailSafeDiagnostic {
    param(
        [object]$Response,
        [ValidateSet('input_read', 'script_digest', 'json_parse', 'event_validate', 'dispatch')]
        [string]$ValidationStage
    )
    $Response['systemMessage'] = "Spark router hook failed validation. validation_stage=$ValidationStage"
    return $Response
}

function Test-HasProperty {
    param([object]$Value, [string]$Name)
    return $null -ne $Value -and $null -ne $Value.PSObject.Properties[$Name]
}

function Test-SparkRole {
    param([string]$AgentType)
    return $AgentType -in $script:SparkRoles
}

function Get-Sha256Hex {
    param([string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '')
    }
    finally { $sha.Dispose() }
}

function Get-FileSha256Hex {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) -join '')
    }
    finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function Copy-ToolInput {
    param([object]$ToolInput)
    $copy = [ordered]@{}
    foreach ($property in $ToolInput.PSObject.Properties) { $copy[$property.Name] = $property.Value }
    return $copy
}

function Get-FallbackPolicy {
    param([object]$ToolInput)
    $message = if (Test-HasProperty $ToolInput 'message') { [string]$ToolInput.message } else { '' }
    $directives = [regex]::Matches($message, '(?im)^[ \t]*fallback_policy[ \t]*:[^\r\n]*$')
    if ($directives.Count -eq 0) { return 'automatic' }
    if ($directives.Count -ne 1) { return 'invalid' }
    $parsed = [regex]::Match($directives[0].Value, '(?i)^[ \t]*fallback_policy[ \t]*:[ \t]*(automatic|pinned)[ \t]*$')
    if (-not $parsed.Success) { return 'invalid' }
    return $parsed.Groups[1].Value.ToLowerInvariant()
}

function Get-WorkUnitId {
    param([object]$ToolInput)
    $message = if (Test-HasProperty $ToolInput 'message') { [string]$ToolInput.message } else { '' }
    $directives = [regex]::Matches($message, '(?im)^[ \t]*work_unit_id[ \t]*:[^\r\n]*$')
    if ($directives.Count -ne 1) { return $null }
    $parsed = [regex]::Match($directives[0].Value, '(?i)^[ \t]*work_unit_id[ \t]*:[ \t]*([A-Za-z0-9._-]{1,128})[ \t]*$')
    if (-not $parsed.Success) { return $null }
    return $parsed.Groups[1].Value
}

function Get-HostCanaryMode {
    param([object]$ToolInput)
    if (-not (Test-HasProperty $ToolInput 'message')) { return 'invalid' }
    $message = [string]$ToolInput.message
    $workUnitLines = [regex]::Matches($message, '(?im)^[ \t]*work_unit_id[ \t]*:[^\r\n]*$')
    if ($workUnitLines.Count -ne 1 -or $null -eq (Get-WorkUnitId $ToolInput)) { return 'invalid' }

    $policyLines = [regex]::Matches($message, '(?im)^[ \t]*fallback_policy[ \t]*:[^\r\n]*$')
    if ($policyLines.Count -ne 1 -or (Get-FallbackPolicy $ToolInput) -ne 'automatic') { return 'invalid' }

    $canaryLines = [regex]::Matches($message, '(?im)^[ \t]*router_v4_canary[ \t]*:[^\r\n]*$')
    if ($canaryLines.Count -ne 1) { return 'invalid' }
    $parsed = [regex]::Match($canaryLines[0].Value, '(?i)^[ \t]*router_v4_canary[ \t]*:[ \t]*(rewrite|deny)[ \t]*$')
    if (-not $parsed.Success) { return 'invalid' }

    # A caller may not pre-seed the receipt label: rewrite must append it exactly once.
    if ([regex]::Matches($message, '(?im)^[ \t]*router_v4_canary_adopted[ \t]*:[^\r\n]*$').Count -ne 0) { return 'invalid' }
    return $parsed.Groups[1].Value.ToLowerInvariant()
}

function New-HostCanaryRewriteResponse {
    param([object]$ToolInput)
    $updated = Copy-ToolInput $ToolInput
    $updated['agent_type'] = 'terra_explorer'
    if ($updated.Contains('model')) { $updated.Remove('model') }
    if ($updated.Contains('reasoning_effort')) { $updated.Remove('reasoning_effort') }
    $originalMessage = [string]$updated['message']
    $separator = if ($originalMessage.EndsWith("`n")) { '' } else { "`n" }
    $updated['message'] = $originalMessage + $separator + 'router_v4_canary_adopted: rewrite'
    return [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'PreToolUse'
            permissionDecision = 'allow'
            updatedInput = $updated
        }
    }
}

function New-FallbackResponse {
    param([object]$ToolInput, [string]$Reason)
    $agentType = [string]$ToolInput.agent_type
    if ($agentType -eq 'spark_explorer') { $target = 'terra_explorer' }
    elseif ($agentType -eq 'spark_patch_worker') { $target = 'terra_worker' }
    else { return $null }

    $updated = Copy-ToolInput $ToolInput
    $updated['agent_type'] = $target
    if ($updated.Contains('model')) { $updated.Remove('model') }
    if ($updated.Contains('reasoning_effort')) { $updated.Remove('reasoning_effort') }
    $originalMessage = if ($updated.Contains('message')) { [string]$updated['message'] } else { '' }
    $updated['message'] = ($originalMessage.TrimEnd() + "`nrouter_v4_fallback_from: $agentType`nrouter_v4_failure_class: model_unavailable`nrouter_v4_reason: $Reason").TrimStart()

    return [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'PreToolUse'
            permissionDecision = 'allow'
            updatedInput = $updated
        }
    }
}

function Test-DateValue {
    param([object]$Value, [switch]$AllowNull)
    if ($null -eq $Value) { return [bool]$AllowNull }
    $parsed = [datetimeoffset]::MinValue
    return [datetimeoffset]::TryParse([string]$Value, [ref]$parsed)
}

function Test-StateInvariant {
    param([object]$State)
    $required = @(
        'schema_version', 'model', 'circuit_state', 'generation', 'failure_kind', 'failure_count',
        'opened_at', 'last_observed_at', 'next_probe_at', 'last_source', 'evidence_sha256',
        'last_failure_fingerprint', 'probe_lease_id', 'probe_generation', 'probe_session_id',
        'probe_turn_id', 'probe_work_unit_id', 'probe_agent_type', 'probe_agent_id',
        'probe_started_at', 'probe_lease_until'
    )
    foreach ($name in $required) { if (-not (Test-HasProperty $State $name)) { return $false } }
    if ([int]$State.schema_version -ne 4 -or [string]$State.model -ne $script:SparkModel) { return $false }
    if ([string]$State.circuit_state -notin @('closed', 'open', 'half_open')) { return $false }
    if ([int64]$State.generation -lt 0 -or [int64]$State.failure_count -lt 0) { return $false }
    if ([string]::IsNullOrWhiteSpace([string]$State.last_source)) { return $false }
    foreach ($hashName in @('evidence_sha256', 'last_failure_fingerprint')) {
        $value = $State.$hashName
        if ($null -ne $value -and [string]$value -notmatch '^[a-f0-9]{64}$') { return $false }
    }
    if (-not (Test-DateValue $State.last_observed_at -AllowNull)) { return $false }

    $leaseNames = @(
        'probe_lease_id', 'probe_generation', 'probe_session_id', 'probe_turn_id',
        'probe_work_unit_id', 'probe_agent_type', 'probe_agent_id', 'probe_started_at', 'probe_lease_until'
    )
    switch ([string]$State.circuit_state) {
        'closed' {
            if ($null -ne $State.failure_kind -or $null -ne $State.opened_at -or $null -ne $State.next_probe_at) { return $false }
            foreach ($name in $leaseNames) { if ($null -ne $State.$name) { return $false } }
        }
        'open' {
            if ([int64]$State.failure_count -lt 1 -or [string]::IsNullOrWhiteSpace([string]$State.failure_kind)) { return $false }
            if (-not (Test-DateValue $State.opened_at) -or -not (Test-DateValue $State.last_observed_at) -or -not (Test-DateValue $State.next_probe_at)) { return $false }
            foreach ($name in $leaseNames) { if ($null -ne $State.$name) { return $false } }
        }
        'half_open' {
            if ([int64]$State.failure_count -lt 1 -or [string]::IsNullOrWhiteSpace([string]$State.failure_kind)) { return $false }
            if (-not (Test-DateValue $State.opened_at) -or -not (Test-DateValue $State.last_observed_at) -or -not (Test-DateValue $State.next_probe_at)) { return $false }
            foreach ($name in @('probe_lease_id', 'probe_generation', 'probe_session_id', 'probe_turn_id', 'probe_work_unit_id', 'probe_agent_type', 'probe_started_at', 'probe_lease_until')) {
                if ($null -eq $State.$name -or [string]::IsNullOrWhiteSpace([string]$State.$name)) { return $false }
            }
            if ([int64]$State.probe_generation -ne [int64]$State.generation) { return $false }
            if (-not (Test-SparkRole ([string]$State.probe_agent_type))) { return $false }
            if ($null -ne $State.probe_agent_id -and [string]::IsNullOrWhiteSpace([string]$State.probe_agent_id)) { return $false }
            if (-not (Test-DateValue $State.probe_started_at) -or -not (Test-DateValue $State.probe_lease_until)) { return $false }
            if ([datetimeoffset]$State.probe_lease_until -le [datetimeoffset]$State.probe_started_at) { return $false }
        }
    }
    return $true
}

function Read-State {
    $state = Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json
    if (-not (Test-StateInvariant $state)) { throw 'state invariant failed' }
    return $state
}

function Write-State {
    param([object]$State)
    if ($InjectWriteFailure) { throw 'injected state write failure' }
    if (-not (Test-StateInvariant $State)) { throw 'refusing invalid state write' }
    $directory = Split-Path -Parent $StatePath
    $nonce = [guid]::NewGuid().ToString('N')
    $temporary = Join-Path $directory ('.model-router-v4.' + $nonce + '.tmp')
    $backup = Join-Path $directory ('.model-router-v4.' + $nonce + '.bak')
    $encoding = New-Object Text.UTF8Encoding -ArgumentList $false
    try {
        [IO.File]::WriteAllText($temporary, ($State | ConvertTo-Json -Depth 20), $encoding)
        if (Test-Path -LiteralPath $StatePath) { [IO.File]::Replace($temporary, $StatePath, $backup, $true) }
        else { [IO.File]::Move($temporary, $StatePath) }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Write-DegradedMarker {
    param([string]$Source, [string]$EvidenceSha256)
    $directory = Split-Path -Parent $script:DegradedPath
    $nonce = [guid]::NewGuid().ToString('N')
    $temporary = Join-Path $directory ('.model-router-v4-degraded.' + $nonce + '.tmp')
    $backup = Join-Path $directory ('.model-router-v4-degraded.' + $nonce + '.bak')
    $encoding = New-Object Text.UTF8Encoding -ArgumentList $false
    $marker = [ordered]@{
        schema_version = 1
        kind = 'spark_circuit_persistence_degraded'
        observed_at = $Now.ToString('o')
        source = $Source
        evidence_sha256 = $EvidenceSha256
    }
    try {
        [IO.File]::WriteAllText($temporary, ($marker | ConvertTo-Json -Depth 10), $encoding)
        if (Test-Path -LiteralPath $script:DegradedPath) { [IO.File]::Replace($temporary, $script:DegradedPath, $backup, $true) }
        else { [IO.File]::Move($temporary, $script:DegradedPath) }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Test-DegradedMarker {
    try { return (Test-Path -LiteralPath $script:DegradedPath -PathType Leaf) }
    catch { return $true }
}

function Repair-DegradedState {
    Invoke-WithStateLock {
        $state = Read-State
        if ([string]$state.circuit_state -eq 'closed') {
            $markerHash = $null
            try {
                $marker = Get-Content -Raw -LiteralPath $script:DegradedPath | ConvertFrom-Json
                if ([string]$marker.evidence_sha256 -match '^[a-f0-9]{64}$') { $markerHash = [string]$marker.evidence_sha256 }
            }
            catch { }
            if ($null -eq $markerHash) { $markerHash = Get-Sha256Hex ('spark_circuit_persistence_degraded|' + $Now.ToString('o')) }
            $state.circuit_state = 'open'
            $state.generation = [int64]$state.generation + 1
            $state.failure_kind = 'persistence_degraded'
            $state.failure_count = [Math]::Max(1, [int]$state.failure_count)
            $state.opened_at = $Now.ToString('o')
            $state.last_observed_at = $Now.ToString('o')
            $state.next_probe_at = $Now.AddMinutes((Get-BackoffMinutes ([int]$state.failure_count))).ToString('o')
            $state.last_source = 'degraded_marker_recovered_to_open'
            $state.evidence_sha256 = $markerHash
            $state.last_failure_fingerprint = $markerHash
            Clear-ProbeLease $state
            Write-State $state
        }
        if (Test-Path -LiteralPath $script:DegradedPath) { Remove-Item -LiteralPath $script:DegradedPath -Force }
    } | Out-Null
}

function Invoke-WithStateLock {
    param([scriptblock]$Action)
    if ($InjectLockFailure) { throw 'injected lock failure' }
    $lockPath = $StatePath + '.lock'
    $deadline = [datetimeoffset]::Now.AddSeconds(2)
    $stream = $null
    while ($null -eq $stream -and [datetimeoffset]::Now -lt $deadline) {
        try { $stream = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
        catch { Start-Sleep -Milliseconds 50 }
    }
    if ($null -eq $stream) { throw 'state lock timeout' }
    try { return (& $Action) }
    finally { $stream.Dispose() }
}

function Clear-ProbeLease {
    param([object]$State)
    foreach ($name in @('probe_lease_id', 'probe_generation', 'probe_session_id', 'probe_turn_id', 'probe_work_unit_id', 'probe_agent_type', 'probe_agent_id', 'probe_started_at', 'probe_lease_until')) { $State.$name = $null }
}

function Get-BackoffMinutes {
    param([int]$FailureCount)
    if ($FailureCount -le 1) { return 360 }
    if ($FailureCount -eq 2) { return 720 }
    return 1440
}

function Get-NextProbeAt {
    param([string]$Message, [int]$FailureCount)
    $hint = [regex]::Match($Message, '(?i)\btry again at\s+([0-9]{1,2}:[0-9]{2}\s*[AP]M)\b')
    if ($hint.Success) {
        $clock = [datetime]::MinValue
        $parsedClock = [datetime]::TryParseExact($hint.Groups[1].Value.ToUpperInvariant(), 'h:mm tt', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AllowWhiteSpaces, [ref]$clock)
        if (-not $parsedClock) {
            $parsedClock = [datetime]::TryParseExact($hint.Groups[1].Value.ToUpperInvariant(), 'hh:mm tt', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AllowWhiteSpaces, [ref]$clock)
        }
        if ($parsedClock) {
            $candidate = New-Object datetimeoffset($Now.Year, $Now.Month, $Now.Day, $clock.Hour, $clock.Minute, 0, $Now.Offset)
            if ($candidate -le $Now) { $candidate = $candidate.AddDays(1) }
            return $candidate.AddMinutes(5)
        }
    }
    return $Now.AddMinutes((Get-BackoffMinutes $FailureCount))
}

function Get-QuotaError {
    param([object]$Container)
    if ($null -eq $Container -or -not (Test-HasProperty $Container 'error')) { return $null }
    $errorObject = $Container.error
    if ($null -eq $errorObject -or -not (Test-HasProperty $errorObject 'codex_error_info') -or -not (Test-HasProperty $errorObject 'message')) { return $null }
    if ([string]$errorObject.codex_error_info -cne 'usage_limit_exceeded') { return $null }
    $message = [string]$errorObject.message
    if ($message.IndexOf('GPT-5.3-Codex-Spark', [StringComparison]::OrdinalIgnoreCase) -lt 0) { return $null }
    if ($message -notmatch '(?i)\busage limit\b') { return $null }
    return $errorObject
}

function Get-QuotaErrorFromToolResponse {
    param([object]$ToolResponse)
    $direct = Get-QuotaError $ToolResponse
    if ($null -ne $direct) { return $direct }
    if (Test-HasProperty $ToolResponse 'structuredContent') {
        $structured = Get-QuotaError $ToolResponse.structuredContent
        if ($null -ne $structured) { return $structured }
    }
    if (Test-HasProperty $ToolResponse 'result') {
        $result = Get-QuotaError $ToolResponse.result
        if ($null -ne $result) { return $result }
    }
    return $null
}

function Get-LatestTranscriptTaskComplete {
    param([string]$TranscriptPath)
    if ([string]::IsNullOrWhiteSpace($TranscriptPath) -or [string]::IsNullOrWhiteSpace($SessionsRoot)) { return $null }
    try {
        $rootFull = [IO.Path]::GetFullPath($SessionsRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
        $pathFull = [IO.Path]::GetFullPath($TranscriptPath)
        if (-not $pathFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) { return $null }
        $stream = New-Object IO.FileStream($pathFull, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            $start = [Math]::Max([int64]0, $stream.Length - $script:TranscriptTailBytes)
            [void]$stream.Seek($start, [IO.SeekOrigin]::Begin)
            $buffer = New-Object byte[] ([int]($stream.Length - $start))
            $offset = 0
            while ($offset -lt $buffer.Length) {
                $count = $stream.Read($buffer, $offset, $buffer.Length - $offset)
                if ($count -le 0) { break }
                $offset += $count
            }
        }
        finally { $stream.Dispose() }
        $text = [Text.Encoding]::UTF8.GetString($buffer, 0, $offset)
        if ($start -gt 0) {
            $firstBreak = $text.IndexOf("`n")
            if ($firstBreak -lt 0) { return $null }
            $text = $text.Substring($firstBreak + 1)
        }
        $lines = @($text -split "\r?\n")
        for ($index = $lines.Count - 1; $index -ge 0; $index--) {
            if ([string]::IsNullOrWhiteSpace($lines[$index])) { continue }
            try { $record = $lines[$index] | ConvertFrom-Json }
            catch { continue }
            if ([string]$record.type -eq 'event_msg' -and (Test-HasProperty $record 'payload') -and [string]$record.payload.type -eq 'task_complete') { return $record.payload }
        }
    }
    catch { return $null }
    return $null
}

function Record-QuotaFailure {
    param([object]$Event, [object]$ErrorObject, [string]$Source)
    $identity = ([string]$Event.session_id) + '|' + ([string]$Event.turn_id)
    $fingerprint = Get-Sha256Hex ($identity + '|' + [string]$ErrorObject.codex_error_info + '|' + [string]$ErrorObject.message)
    Invoke-WithStateLock {
        $state = Read-State
        if ([string]$state.last_failure_fingerprint -eq $fingerprint) { return }
        $newFailureCount = [int]$state.failure_count + 1
        $state.circuit_state = 'open'
        $state.generation = [int64]$state.generation + 1
        $state.failure_kind = 'usage_limit_exceeded'
        $state.failure_count = $newFailureCount
        $state.opened_at = $Now.ToString('o')
        $state.last_observed_at = $Now.ToString('o')
        $state.next_probe_at = (Get-NextProbeAt ([string]$ErrorObject.message) $newFailureCount).ToString('o')
        $state.last_source = $Source
        $state.evidence_sha256 = $fingerprint
        $state.last_failure_fingerprint = $fingerprint
        Clear-ProbeLease $state
        Write-State $state
    } | Out-Null
}

function Get-PreToolResponse {
    param([object]$Event)
    $toolInput = $Event.tool_input
    if ($null -eq $toolInput -or -not (Test-HasProperty $toolInput 'agent_type')) { return New-EmptyResponse }
    if ([string]$toolInput.agent_type -eq $script:RouterV4HostCanaryAgentType) {
        $canaryMode = Get-HostCanaryMode $toolInput
        if ($canaryMode -eq 'invalid') { return New-DenyResponse 'router_v4_canary_invalid' }
        if ($canaryMode -eq 'deny') { return New-DenyResponse 'router_v4_canary_deny' }
        return New-HostCanaryRewriteResponse $toolInput
    }
    if (-not (Test-SparkRole ([string]$toolInput.agent_type))) { return New-EmptyResponse }
    $policy = Get-FallbackPolicy $toolInput
    if ($policy -eq 'invalid') { return New-DenyResponse 'spark_router_invalid_fallback_policy' }
    if ($policy -eq 'pinned') { return New-DenyResponse 'spark_router_pinned_provider_probe_disabled' }
    # This kill-switch is script-owned: hook input and task prompts cannot enable it.
    if (-not $script:AutomaticSparkProviderProbeEnabled) {
        return New-FallbackResponse $toolInput 'spark_provider_probe_disabled'
    }
    return New-DenyResponse 'spark_router_provider_probe_not_manually_enabled'
}

function Get-SessionStartResponse {
    return New-ContextResponse 'SessionStart' 'Spark profile hard kill-switch is active and automatic provider probes are disabled. Route automatic Spark candidates to Terra; deny pinned Spark requests. Hook installation or trust does not prove host enforcement.'
}

function Get-SubagentStartResponse {
    param([object]$Event)
    if (-not $script:AutomaticSparkProviderProbeEnabled) { return New-EmptyResponse }
    if (-not (Test-SparkRole ([string]$Event.agent_type)) -or [string]::IsNullOrWhiteSpace([string]$Event.agent_id)) { return New-EmptyResponse }
    try {
        return Invoke-WithStateLock {
            $state = Read-State
            if ([string]$state.circuit_state -ne 'half_open' -or $Now -ge [datetimeoffset]$state.probe_lease_until) { return New-EmptyResponse }
            if ([string]$Event.model -ne $script:SparkModel -or [string]$Event.session_id -ne [string]$state.probe_session_id -or [string]$Event.turn_id -ne [string]$state.probe_turn_id -or [string]$Event.agent_type -ne [string]$state.probe_agent_type) { return New-EmptyResponse }
            if ($null -eq $state.probe_agent_id) {
                $state.probe_agent_id = [string]$Event.agent_id
                $state.last_observed_at = $Now.ToString('o')
                $state.last_source = 'half_open_probe_started'
                Write-State $state
            }
            elseif ([string]$state.probe_agent_id -ne [string]$Event.agent_id) { return New-EmptyResponse }
            return New-ContextResponse 'SubagentStart' "This is Spark availability probe lease $($state.probe_lease_id), generation $($state.probe_generation), work_unit_id $($state.probe_work_unit_id). Preserve the exact lease-bound _route_receipt instruction from the task packet."
        }
    }
    catch { return New-EmptyResponse }
}

function Get-PostToolResponse {
    param([object]$Event)
    $errorObject = Get-QuotaErrorFromToolResponse $Event.tool_response
    if ($null -eq $errorObject) { return New-EmptyResponse }
    try { Record-QuotaFailure $Event $errorObject 'post_tool_response' }
    catch {
        $fingerprint = Get-Sha256Hex (([string]$Event.session_id) + '|' + ([string]$Event.turn_id) + '|' + [string]$errorObject.codex_error_info + '|' + [string]$errorObject.message)
        try { Write-DegradedMarker 'post_tool_quota_persistence_failure' $fingerprint }
        catch { }
        return New-SystemMessageResponse 'Spark quota evidence could not be committed to the primary circuit state. The router entered fail-closed degraded mode; automatic routes must use Terra.'
    }
    return New-EmptyResponse
}

function Get-SubagentStopResponse {
    param([object]$Event)
    if (-not (Test-SparkRole ([string]$Event.agent_type))) { return New-EmptyResponse }
    try {
        $terminal = Get-LatestTranscriptTaskComplete ([string]$Event.agent_transcript_path)
        $quotaError = Get-QuotaError $terminal
        if ($null -ne $quotaError) {
            try { Record-QuotaFailure $Event $quotaError 'subagent_transcript_task_complete' }
            catch {
                $fingerprint = Get-Sha256Hex (([string]$Event.session_id) + '|' + ([string]$Event.turn_id) + '|' + [string]$quotaError.codex_error_info + '|' + [string]$quotaError.message)
                try { Write-DegradedMarker 'subagent_quota_persistence_failure' $fingerprint }
                catch { }
                return New-SystemMessageResponse 'Spark quota evidence could not be committed to the primary circuit state. The router entered fail-closed degraded mode; automatic routes must use Terra.'
            }
            return New-EmptyResponse
        }
    }
    catch { }
    return New-EmptyResponse
}

function Get-FailSafeResponse {
    param(
        [string]$EventName,
        [object]$ParsedEvent,
        [ValidateSet('input_read', 'script_digest', 'json_parse', 'event_validate', 'dispatch')]
        [string]$ValidationStage
    )
    if ($EventName -eq 'SessionStart') {
        return New-ContextResponse 'SessionStart' "Spark router hook failed validation. Treat Spark as unavailable and route eligible work to Terra. validation_stage=$ValidationStage"
    }
    if ($EventName -eq 'PreToolUse') {
        if ($null -eq $ParsedEvent -or -not (Test-HasProperty $ParsedEvent 'tool_input')) { return Add-FailSafeDiagnostic (New-DenyResponse 'spark_router_malformed_hook_input') $ValidationStage }
        $toolInput = $ParsedEvent.tool_input
        if ($null -eq $toolInput -or -not (Test-SparkRole ([string]$toolInput.agent_type))) { return Add-FailSafeDiagnostic (New-EmptyResponse) $ValidationStage }
        $policy = Get-FallbackPolicy $toolInput
        if ($policy -ne 'automatic') { return Add-FailSafeDiagnostic (New-DenyResponse 'spark_router_fail_closed') $ValidationStage }
        try {
            $fallback = New-FallbackResponse $toolInput 'spark_router_fail_closed'
            if ($null -ne $fallback) { return Add-FailSafeDiagnostic $fallback $ValidationStage }
        }
        catch { }
        return Add-FailSafeDiagnostic (New-DenyResponse 'spark_router_fail_closed') $ValidationStage
    }
    return New-EmptyResponse
}

$parsedEvent = $null
$eventName = $ExpectedEvent
$validationStage = 'input_read'
try {
    if ([string]::IsNullOrWhiteSpace($HookInputJson)) {
        $stdinStream = [Console]::OpenStandardInput()
        try {
            $utf8Strict = New-Object Text.UTF8Encoding -ArgumentList $true, $true
            $stdinReader = New-Object IO.StreamReader -ArgumentList $stdinStream, $utf8Strict, $true
            try { $HookInputJson = $stdinReader.ReadToEnd() }
            finally { $stdinReader.Dispose() }
        }
        finally { $stdinStream.Dispose() }
    }
    if ([string]::IsNullOrWhiteSpace($HookInputJson)) { throw 'empty hook input' }
    $validationStage = 'script_digest'
    if (-not [string]::IsNullOrWhiteSpace($ExpectedScriptSha256)) {
        if ($ExpectedScriptSha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'invalid expected script digest' }
        $actualScriptSha256 = Get-FileSha256Hex $PSCommandPath
        if ($actualScriptSha256 -cne $ExpectedScriptSha256.ToLowerInvariant()) { throw 'script digest mismatch' }
    }
    $validationStage = 'json_parse'
    $parsedEvent = $HookInputJson | ConvertFrom-Json
    $validationStage = 'event_validate'
    if ([string]::IsNullOrWhiteSpace($eventName)) { $eventName = [string]$parsedEvent.hook_event_name }
    if ([string]$parsedEvent.hook_event_name -ne $eventName) { throw 'hook event mismatch' }
    $validationStage = 'dispatch'
    switch ($eventName) {
        'SessionStart' { $response = Get-SessionStartResponse }
        'PreToolUse' { $response = Get-PreToolResponse $parsedEvent }
        'PostToolUse' { $response = Get-PostToolResponse $parsedEvent }
        'SubagentStart' { $response = Get-SubagentStartResponse $parsedEvent }
        'SubagentStop' { $response = Get-SubagentStopResponse $parsedEvent }
        default { $response = Get-FailSafeResponse $eventName $parsedEvent $validationStage }
    }
}
catch { $response = Get-FailSafeResponse $eventName $parsedEvent $validationStage }

$response | ConvertTo-Json -Compress -Depth 20
