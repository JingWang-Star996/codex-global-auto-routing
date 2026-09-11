[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$agents = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $root 'AGENTS.example.md')
$doc = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $root 'docs\upward-assist-r10.md')
$qa = Join-Path $root 'tests\.release-test-output'
[IO.Directory]::CreateDirectory($qa) | Out-Null
$assertions = 0
function Assert-Text([bool]$Value, [string]$Name) { if (-not $Value) { throw "FAILED: $Name" }; $script:assertions++ }

Assert-Text ($agents -match '默认关闭，仅当当前根任务有用户明确具体授权时才可启用') 'default requires current-root authorization'
Assert-Text ($agents -match '不把每个任务变成例行询问') 'normal execution before routine asking'
Assert-Text ($agents -match '命中既有升级条件.*主动申请一次') 'one proactive request when eligible'
Assert-Text ($agents -match '启动即有具体独立复核证据时可提前申请') 'early request without manufactured failure'
Assert-Text ($agents -match '已有具体有效预授权时不重复询问.*不强制调用') 'preauthorization is not mandatory invocation'
Assert-Text ($agents -match '拒绝后不主动再问.*未回复或模糊回复均非授权') 'deny silence ambiguity handling'
Assert-Text ($agents -match '不预占、不调用') 'no reservation after missing approval'
Assert-Text ($agents -match '授权仅限当前根，撤销优先') 'root-only revocable authorization'
Assert-Text ($agents -match '预占前撤销则不预占') 'withdrawal before reserve'
Assert-Text ($agents -match '已预占未 spawn 则不 spawn 且名额保持消耗') 'withdrawal after reserve before spawn'
Assert-Text ($agents -match 'spawn 已发出而 child 仍运行则只请求中断一次并读回终态，不重试') 'withdrawal after spawn'
Assert-Text ($agents -match '普通工具/测试失败、quota、登录权限或需求歧义不触发 Astra') 'ordinary blockers excluded'

Assert-Text ($doc -match '## 用户授权的三种时机') 'timing documentation exists'
Assert-Text ($doc -match '不得为了获得授权故意制造失败') 'no manufactured failure in documentation'
Assert-Text ($doc -match '最多一次额外用量.*不承诺精确费用') 'cost boundary documented'
Assert-Text ($doc -match '主模型不会改变') 'coordinator model remains stable'
Assert-Text ($doc -match '未回复和模糊回复也不是授权') 'wait behavior documented'
Assert-Text ($doc -match '不能复活已经消耗的 reservation') 'consumed ledger not revived'
Assert-Text ($doc -match '在 `reserve` 前收到撤销时，不预占') 'documented withdrawal before reserve'
Assert-Text ($doc -match '已经 `reserve` 但尚未发出 spawn 时，不 spawn，且 reservation 继续消耗') 'documented withdrawal after reserve'
Assert-Text ($doc -match 'spawn 已发出且 child 仍运行时，只请求中断一次并读回终态，不再重试') 'documented withdrawal after spawn'
Assert-Text ($doc -match 'provider 调用和相应用量可能无法撤回') 'provider consumption caveat'
Assert-Text ($doc -match '发布包不含私人部署摘要、机器哈希、真实任务 ID 或原始历史证据') 'portable package removes historical deployment records'
Assert-Text ($doc -match '不能把离线测试当作 live 或正向 child 证明') 'offline boundary retained'

$result = [ordered]@{ assertions_passed = $assertions; static_only = $true; runtime_proof = $false; agents_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root 'AGENTS.example.md')).Hash.ToLowerInvariant(); doc_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root 'docs\upward-assist-r10.md')).Hash.ToLowerInvariant() }
$output = Join-Path $qa 'policy-timing.json'
[IO.File]::WriteAllText($output, ($result | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
$result | ConvertTo-Json -Compress
