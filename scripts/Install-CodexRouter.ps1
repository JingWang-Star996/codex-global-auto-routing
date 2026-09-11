[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourceRoot,
    [Parameter(Mandatory = $true)][string]$TargetCodexHome,
    [string]$TemplatePath = '',
    [string]$ApprovedTokenSha256 = '',
    [string]$ExpectedHooksSha256 = '',
    [switch]$PlanOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-Digest { param([string]$Path); (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Test-Keys {
    param($Object, [string[]]$Expected)
    if ($null -eq $Object) { return $false }
    $a = @($Object.PSObject.Properties.Name | Sort-Object)
    $b = @($Expected | Sort-Object)
    return $a.Count -eq $b.Count -and (@(Compare-Object $a $b).Count -eq 0)
}
function Router-Command {
    param([string]$Root, [string]$Event, [string]$Hash)
    'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $Root ('hooks\spark-router-circuit.'+$Hash+'.ps1')) + '" -StatePath "' + (Join-Path $Root 'state\model-router-v4.json') + '" -SessionsRoot "' + (Join-Path $Root 'sessions') + '" -ExpectedEvent "' + $Event + '" -ExpectedScriptSha256 "' + $Hash + '"'
}
function Assert-Router {
    param($Document, [string]$Root, [string]$RequiredHash = '', [bool]$CheckFiles = $true, [bool]$AllowToken = $false)
    if (-not (Test-Keys $Document @('description','hooks')) -or [string]$Document.description -notmatch '^codex-global-auto-routing;') { throw 'Unknown hooks manifest owner or properties.' }
    $events = @('SessionStart','PreToolUse','PostToolUse','SubagentStart','SubagentStop')
    if ($AllowToken) { $events += 'Stop' }
    if (-not (Test-Keys $Document.hooks $events)) { throw 'Unknown or missing Hook events.' }
    $matchers = @{SessionStart=$null;PreToolUse='^(Agent|spawn_agent)$';PostToolUse='^(Agent|spawn_agent)$';SubagentStart='^(spark_explorer|spark_patch_worker)$';SubagentStop='^(spark_explorer|spark_patch_worker)$'}
    $statuses = @{SessionStart='Loading disabled Spark router';PreToolUse='Observing route request; coordinator policy authoritative';PostToolUse='Recording Spark availability evidence';SubagentStart='Spark provider probe disabled';SubagentStop='Recording Spark availability evidence'}
    $seenHash = ''
    foreach ($eventName in @('SessionStart','PreToolUse','PostToolUse','SubagentStart','SubagentStop')) {
        $entries = @($Document.hooks.$eventName)
        $count = if ($AllowToken -and $eventName -eq 'SubagentStop') {2} else {1}
        if ($entries.Count -ne $count) { throw "Duplicate or missing $eventName entries." }
        $props = if ($eventName -eq 'SessionStart') {@('hooks')} else {@('matcher','hooks')}
        if (-not (Test-Keys $entries[0] $props)) { throw "Invalid $eventName entry properties." }
        if ($eventName -ne 'SessionStart' -and [string]$entries[0].matcher -cne $matchers[$eventName]) { throw "Invalid $eventName matcher." }
        $handlers = @($entries[0].hooks)
        $props = @('type','command','commandWindows','timeout','statusMessage')
        if ($eventName -ne 'SubagentStop') { $props += 'additionalContextLimit' }
        if ($handlers.Count -ne 1 -or -not (Test-Keys $handlers[0] $props)) { throw "Invalid $eventName handler properties." }
        $h = $handlers[0]
        if ($h.type -cne 'command' -or $h.timeout -ne 5 -or $h.statusMessage -cne $statuses[$eventName]) { throw "Invalid $eventName handler values." }
        if ($eventName -ne 'SubagentStop' -and $h.additionalContextLimit -ne 500) { throw 'Unexpected additionalContextLimit.' }
        $m = [regex]::Match([string]$h.command, 'spark-router-circuit\.([0-9a-f]{64})\.ps1')
        if (-not $m.Success) { throw 'Router command lacks a canonical digest.' }
        $hash = $m.Groups[1].Value
        if ($RequiredHash -and $hash -cne $RequiredHash) { throw 'Rendered router hash mismatch.' }
        if ($seenHash -and $seenHash -cne $hash) { throw 'Mixed router versions.' }
        $seenHash = $hash
        $expected = Router-Command $Root $eventName $hash
        if ($h.command -cne $expected -or $h.commandWindows -cne $expected) { throw 'Unknown router command.' }
        if ($CheckFiles) {
            $file = Join-Path $Root ('hooks\spark-router-circuit.'+$hash+'.ps1')
            if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Digest $file) -cne $hash) { throw 'Router script digest mismatch.' }
        }
    }
}
function Assert-TokenPair {
    param($Document, [string]$Root, [string]$ApprovedHash)
    if ($ApprovedHash -notmatch '^[0-9a-fA-F]{64}$') { throw 'Preserving Token handlers requires explicit ApprovedTokenSha256.' }
    $hash = $ApprovedHash.ToLowerInvariant()
    $stop = @($Document.hooks.Stop)
    $sub = @($Document.hooks.SubagentStop)
    if ($stop.Count -ne 1 -or $sub.Count -ne 2) { throw 'Token pair missing or duplicated.' }
    $signature = ''
    foreach ($entry in @($stop[0], $sub[1])) {
        if (-not (Test-Keys $entry @('hooks')) -or @($entry.hooks).Count -ne 1) { throw 'Token entry must be a single matcher-free handler.' }
        $h = $entry.hooks[0]
        if (-not (Test-Keys $h @('type','command','commandWindows','timeout','statusMessage')) -or $h.type -cne 'command' -or $h.timeout -notin @(5,15) -or $h.statusMessage -cne 'Reporting token usage') { throw 'Unknown Token handler values.' }
        $prefix = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'
        $suffix = '" -SessionsRoot "'+(Join-Path $Root 'sessions')+'" -ReportsRoot "'+(Join-Path $Root 'state\token-usage-reports')+'"'
        $addressed = Join-Path $Root ('hooks\token-usage-report.'+$hash+'.ps1')
        $legacy = Join-Path $Root 'hooks\token-usage-report.ps1'
        $addressedCommand = $prefix+$addressed+$suffix+' -ExpectedScriptSha256 "'+$hash+'"'
        $legacyCommand = $prefix+$legacy+$suffix
        $file = if ($h.command -ceq $addressedCommand) {$addressed} elseif ($h.command -ceq $legacyCommand) {$legacy} else {throw 'Unknown Token command or unapproved digest.'}
        if ($h.commandWindows -cne $h.command -or -not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Digest $file) -cne $hash) { throw 'Token command/file integrity mismatch.' }
        # Preserve both handlers exactly, including settings. The router never owns their implementation.
        $current = $h | ConvertTo-Json -Depth 10 -Compress
        if ($signature -and $signature -cne $current) { throw 'Token pair differs.' }
        $signature = $current
    }
}
function Assert-Snapshot {
    param([string]$Path, [string]$Expected)
    $now = if (Test-Path -LiteralPath $Path -PathType Leaf) {Get-Digest $Path} else {'absent'}
    if ($now -cne $Expected) { throw 'hooks.json changed after validation; refusing replacement.' }
}
function Install-Immutable {
    param([string]$Source, [string]$Destination, [string]$Hash)
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if ((Get-Digest $Destination) -cne $Hash) { throw 'Content-addressed destination is corrupt.' }
        return
    }
    $temp = Join-Path (Split-Path $Destination -Parent) ('.router-'+[guid]::NewGuid().ToString('N')+'.tmp')
    try {
        [IO.File]::WriteAllBytes($temp,[IO.File]::ReadAllBytes($Source))
        if ((Get-Digest $temp) -cne $Hash) { throw 'Source changed during copy.' }
        try { [IO.File]::Move($temp,$Destination) }
        catch { if (-not (Test-Path -LiteralPath $Destination -PathType Leaf) -or (Get-Digest $Destination) -cne $Hash) {throw} }
    } finally { if (Test-Path -LiteralPath $temp -PathType Leaf) {Remove-Item -LiteralPath $temp -Force} }
}
$source = [IO.Path]::GetFullPath($SourceRoot)
$target = [IO.Path]::GetFullPath($TargetCodexHome).TrimEnd('\')
$script = Join-Path $source 'hooks\spark-router-circuit.ps1'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {throw 'Router source missing.'}
if (-not $TemplatePath) {$TemplatePath = Join-Path $source 'hooks.example.json'}
$hash = Get-Digest $script
$hooks = Join-Path $target 'hooks.json'
$initial = if (Test-Path -LiteralPath $hooks -PathType Leaf) {Get-Digest $hooks} else {'absent'}
if ($initial -ne 'absent' -and $ExpectedHooksSha256 -notmatch '^[0-9a-fA-F]{64}$') {throw 'Existing hooks.json requires a valid ExpectedHooksSha256 before any write.'}
if ($ExpectedHooksSha256 -and $initial -cne $ExpectedHooksSha256.ToLowerInvariant()) {throw 'ExpectedHooksSha256 does not match current hooks.json.'}
$old = $null
$hasToken = $false
if ($initial -ne 'absent') {
    try {
        $old = Get-Content -LiteralPath $hooks -Raw -Encoding UTF8 | ConvertFrom-Json
        $hasToken = $null -ne $old.hooks.PSObject.Properties['Stop']
        Assert-Router $old $target '' $true $hasToken
        if ($hasToken) {Assert-TokenPair $old $target $ApprovedTokenSha256}
    } catch { throw ('Existing hooks.json is not managed exclusively by the canonical router and approved Token pair: '+$_.Exception.Message) }
    Assert-Snapshot $hooks $initial
}
$rendered = Get-Content -LiteralPath $TemplatePath -Raw -Encoding UTF8 | ConvertFrom-Json
$rendered.description = 'codex-global-auto-routing; managed live Hook. Standard input must be UTF-8 (BOM is allowed); the digest detects deployment drift and does not prove host enforcement.'
foreach ($eventName in @($rendered.hooks.PSObject.Properties.Name)) {
    foreach ($entry in @($rendered.hooks.$eventName)) {
        foreach ($handler in @($entry.hooks)) {
            foreach ($key in @('command','commandWindows')) {
                $handler.$key = ([string]$handler.$key).Replace('%CODEX_HOME%',$target).Replace('__SCRIPT_SHA256__',$hash)
            }
        }
    }
}
Assert-Router $rendered $target $hash $false $false
if ($hasToken) {
    $rendered.hooks.SubagentStop = @($rendered.hooks.SubagentStop) + @($old.hooks.SubagentStop[1])
    $rendered.hooks | Add-Member -NotePropertyName Stop -NotePropertyValue @($old.hooks.Stop)
}
$text = $rendered | ConvertTo-Json -Depth 20 -Compress
$sha = [Security.Cryptography.SHA256]::Create()
try {$renderedHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text)))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
$directory = Join-Path $target 'hooks'
$destination = Join-Path $directory ('spark-router-circuit.'+$hash+'.ps1')
if (Test-Path -LiteralPath $destination -PathType Leaf) {
    if ((Get-Digest $destination) -cne $hash) {throw 'Existing content-addressed script differs.'}
}
Assert-Snapshot $hooks $initial
$receipt = [ordered]@{plan_only=[bool]$PlanOnly;router_sha256=$hash;router_path=$destination;token_preserved=$hasToken;token_sha256=$(if($hasToken){$ApprovedTokenSha256.ToLowerInvariant()}else{$null});previous_hooks_sha256=$initial;hooks_sha256=$renderedHash;previous_hooks_backup=$null;changed=($initial -cne $renderedHash);restart_required=($initial -cne $renderedHash);host_execution_proof=$false}
$receipt.script_sha256 = $hash
$receipt.script_path = $destination
if ($PlanOnly) {$receipt | ConvertTo-Json -Compress; return}
[IO.Directory]::CreateDirectory($directory) | Out-Null
Install-Immutable $script $destination $hash
Assert-Snapshot $hooks $initial
if ($hasToken) {Assert-TokenPair $old $target $ApprovedTokenSha256}
if ($initial -cne $renderedHash) {
    $temp = Join-Path $target ('.hooks-'+[guid]::NewGuid().ToString('N')+'.tmp')
    try {
        [IO.File]::WriteAllText($temp,$text,(New-Object Text.UTF8Encoding($false)))
        Assert-Snapshot $hooks $initial
        if ($initial -eq 'absent') {[IO.File]::Move($temp,$hooks)}
        else {
            $history = Join-Path $directory 'history'
            [IO.Directory]::CreateDirectory($history) | Out-Null
            $backup = Join-Path $history ('hooks.'+$initial+'.'+[guid]::NewGuid().ToString('N')+'.json')
            Assert-Snapshot $hooks $initial
            [IO.File]::Replace($temp,$hooks,$backup)
            $receipt.previous_hooks_backup = $backup
            if ((Get-Digest $backup) -cne $initial) {throw 'Concurrent replacement detected; retained backup for manual recovery.'}
        }
    } finally {if(Test-Path -LiteralPath $temp -PathType Leaf){Remove-Item -LiteralPath $temp -Force}}
}
if ((Get-Digest $hooks) -cne $renderedHash) {throw 'Post-install hooks digest mismatch.'}
$receipt | ConvertTo-Json -Compress
