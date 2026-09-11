[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$en=Join-Path $root 'i18n\en'
$qa=Join-Path $root 'tests\.release-test-output'; [IO.Directory]::CreateDirectory($qa)|Out-Null
$count=0
function Check([bool]$ok,[string]$name){if(-not $ok){throw "FAILED: $name"};$script:count++}
Check (Test-Path -LiteralPath (Join-Path $en 'AGENTS.example.md') -PathType Leaf) 'English policy exists'
Check (Test-Path -LiteralPath (Join-Path $en 'docs\upward-assist-r10.md') -PathType Leaf) 'English R10 document exists'
$roles=@('astra-specialist','luna-batch-worker','sol-specialist','spark-explorer','spark-patch-worker','terra-explorer','terra-worker')
foreach($role in $roles){
 $zhPath=Join-Path $root ('agents\'+$role+'.toml');$enPath=Join-Path $en ('agents\'+$role+'.toml')
 Check (Test-Path -LiteralPath $enPath -PathType Leaf) ($role+' English profile exists')
 $zh=Get-Content -Raw -Encoding UTF8 -LiteralPath $zhPath;$translated=Get-Content -Raw -Encoding UTF8 -LiteralPath $enPath
 foreach($key in @('name','model','model_reasoning_effort','sandbox_mode')){
  $rx='(?m)^'+$key+' = "[^"]+"'; Check ([regex]::Match($zh,$rx).Value -ceq [regex]::Match($translated,$rx).Value) ($role+' identical '+$key)
 }
 Check ($translated -match '(?m)^developer_instructions = """') ($role+' instructions retained')
}
$policy=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $en 'AGENTS.example.md')
$doc=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $en 'docs\upward-assist-r10.md')
$zhPolicyLines=Get-Content -Encoding UTF8 -LiteralPath (Join-Path $root 'AGENTS.example.md')
$enPolicyLines=Get-Content -Encoding UTF8 -LiteralPath (Join-Path $en 'AGENTS.example.md')
$zhDocLines=Get-Content -Encoding UTF8 -LiteralPath (Join-Path $root 'docs\upward-assist-r10.md')
$enDocLines=Get-Content -Encoding UTF8 -LiteralPath (Join-Path $en 'docs\upward-assist-r10.md')
Check ((@($zhPolicyLines|Where-Object {$_ -match '^## '}).Count) -eq (@($enPolicyLines|Where-Object {$_ -match '^## '}).Count)) 'policy H2 count parity'
Check ((@($zhPolicyLines|Where-Object {$_ -match '^- '}).Count) -eq (@($enPolicyLines|Where-Object {$_ -match '^- '}).Count)) 'policy bullet count parity'
Check ((@($zhDocLines|Where-Object {$_ -match '^## '}).Count) -eq (@($enDocLines|Where-Object {$_ -match '^## '}).Count)) 'document H2 count parity'
Check ((@($zhDocLines|Where-Object {$_ -match '^- '}).Count) -eq (@($enDocLines|Where-Object {$_ -match '^- '}).Count)) 'document bullet count parity'
Check ((@($zhDocLines|Where-Object {$_ -match '^\d+\. '}).Count) -eq (@($enDocLines|Where-Object {$_ -match '^\d+\. '}).Count)) 'document numbered-step parity'
foreach($fragment in @('gpt-5.6-sol','gpt-6-astra','astra_specialist','fork_turns="none"','8000','3000','180 seconds','half_open','Spark','pinned Spark requests are rejected','<CODEX_HOME>/state/upward-assist-r10','bounded_complexity','unresolved_evidence_conflict','independent_cross_model_review','model_unavailable','task_or_validation_failure','scope_or_risk_escalation','permission_or_user_gate','not host spawn enforcement','reservation_created','provider_attempt_observed','revocation wins')){Check ($policy.Contains($fragment)) ('policy '+$fragment)}
foreach($fragment in @('Reuse the existing worker','actual_model/actual_sandbox','codex_error_info=usage_limit_exceeded','at most two child roles','Before writer handoff','Human-readable time guidance','controlled small samples')){Check ($policy.Contains($fragment)) ('policy detail '+$fragment)}
foreach($fragment in @('Prefer combining short tasks','serializing steps that strongly depend on the same context','not Astra''s automatic upgrade tier','ordinary architecture explanation is not delegated')){Check ($policy.Contains($fragment)) ('routing equivalence '+$fragment)}
foreach($fragment in @('<CODEX_HOME>/state/upward-assist-r10','schema_valid=true','allowed=false','can_spawn=false','maximum 32 KiB','8000','3000','gpt-5.6-sol','gpt-6-astra/high','bounded_complexity','unresolved_evidence_conflict','independent_cross_model_review','not host authentication','One reservation, one spawn, one child turn','Offline tests are not live deployment')){Check ($doc.Contains($fragment)) ('document '+$fragment)}
foreach($fragment in @('diagnostic harness is limited to that R10 integration run','never reuse it as business-task authorization','not evidence of a successful post-fix analysis','separate explicit authorization in a new Sol root')){Check ($doc.Contains($fragment)) ('document equivalence '+$fragment)}
Check ($doc.Contains('"$env:CODEX_HOME\scripts\upward_assist.py"') -and $doc.Contains('"$requestPath"')) 'quoted portable PowerShell commands'
Check (-not ($policy -match 'C:\\Users\\|E:\\Codexindex')) 'policy has no private absolute paths'
Check (-not ($doc -match 'C:\\Users\\|E:\\Codexindex')) 'document has no private absolute paths'
$result=[ordered]@{assertions_passed=$count;static_only=$true;runtime_proof=$false;roles=$roles;english_policy_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $en 'AGENTS.example.md')).Hash.ToLowerInvariant();english_doc_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $en 'docs\upward-assist-r10.md')).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $qa 'bilingual-parity.json'),($result|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
$result|ConvertTo-Json -Compress
