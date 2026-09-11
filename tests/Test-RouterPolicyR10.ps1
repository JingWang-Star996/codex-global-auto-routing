[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$policy=Get-Content -LiteralPath (Join-Path $root 'AGENTS.example.md') -Raw -Encoding UTF8
$passed=0
function Check { param([bool]$Ok,[string]$Name); if(-not $Ok){throw "FAIL $Name"}; $script:passed++; "PASS $Name" }
foreach($fragment in @('全局模型路由 R10','不因“超过 10 秒”','每次必须精确设置','同模型也不例外','fork_turns="none"','delegation_reason','independence_required','实名与身份验证','购买','验证码','不可逆迁移','禁止 Spark provider 调用','half_open','pinned Spark 请求拒绝','可信生命周期持久化','人工审阅','configured_sandbox','turn_context','writer_epoch','中断 30 秒','原因明确','重验一次','cached 是 input 子项','不等于账单费用','默认关闭','gpt-5.6-sol','不是宿主','一个根任务仅一次机会','provider_attempt_observed','180 秒','不 follow-up','8000 字符','3000 字符')){
 Check ($policy.Contains($fragment)) ('invariant '+$fragment)
}
foreach($name in @('terra-explorer','terra-worker','sol-specialist','luna-batch-worker')){
 $p=Get-Content -LiteralPath (Join-Path $root ('agents\'+$name+'.toml')) -Raw -Encoding UTF8
 foreach($key in @('model','model_reasoning_effort','sandbox_mode','developer_instructions')){
  Check ($p -match ('(?m)^'+$key+' = ')) ($name+' has portable '+$key)
 }
 Check ($p.Contains('"configured_sandbox"') -and -not $p.Contains('"sandbox":')) ($name+' configured receipt')
}
$astra=Get-Content -LiteralPath (Join-Path $root 'agents\astra-specialist.toml') -Raw -Encoding UTF8
foreach($fragment in @('name = "astra_specialist"','model = "gpt-6-astra"','model_reasoning_effort = "high"','sandbox_mode = "read-only"','[agents]','enabled = false','不要执行工具','禁止修改文件','发起任何子 Agent','不作整个用户任务的完成声明','configured_sandbox')){
 Check ($astra.Contains($fragment)) ('Astra '+$fragment)
}
$sol=Get-Content -LiteralPath (Join-Path $root 'agents\sol-specialist.toml') -Raw -Encoding UTF8
Check ($sol.Contains('不得预占、发起、指挥或嵌套委派')) 'Sol child cannot initiate upward request'
$doc=Get-Content -LiteralPath (Join-Path $root 'docs\upward-assist-r10.md') -Raw -Encoding UTF8
foreach($fragment in @('不是安全认证或宿主强制路由','<CODEX_HOME>/state/upward-assist-r10','不检查账本是否已占用','不删除资格账本','不宣称节省 Token')){
 Check ($doc.Contains($fragment)) ('boundary '+$fragment)
}
$result=[ordered]@{passed=$passed;policy_chars=$policy.Length;policy_sha256=(Get-FileHash -LiteralPath (Join-Path $root 'AGENTS.example.md')).Hash.ToLowerInvariant();scope='static policy/profile invariants only';runtime_routing_proof=$false;performance_proof=$false}
$qa=Join-Path $root 'tests\.release-test-output'; [IO.Directory]::CreateDirectory($qa)|Out-Null
$result|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $qa 'policy.json') -Encoding UTF8
"PASSED=$passed"
