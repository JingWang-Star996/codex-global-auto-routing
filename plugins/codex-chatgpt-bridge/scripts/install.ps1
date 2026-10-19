#requires -Version 7.0
param([switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$bridgeRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$bridgeServer = Join-Path $bridgeRoot 'src/server.mjs'
if (-not (Test-Path -LiteralPath $bridgeServer -PathType Leaf)) { throw 'Missing bridge server' }
$bridgeMcp = @{ mcpServers = @{ chatgpt_bridge = @{ command = 'node'; args = @($bridgeServer, '--stdio') } } }
$bridgeMcp | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $bridgeRoot '.mcp.json') -Encoding utf8NoBOM
if ($PrepareOnly) { Write-Output 'Prepared local MCP entry; no Codex configuration or browser changed.'; return }
Get-Command node,codex -ErrorAction Stop | Out-Null
& codex plugin marketplace add $bridgeRoot --json
if ($LASTEXITCODE -ne 0) { throw 'Marketplace registration failed' }
& codex plugin add 'codex-chatgpt-bridge@local-chatgpt-bridge' --json
if ($LASTEXITCODE -ne 0) { throw 'Plugin installation failed' }
Write-Output 'Installed. Reload tool discovery if needed. Keep this source folder. Do not commit the generated machine-specific .mcp.json.'
