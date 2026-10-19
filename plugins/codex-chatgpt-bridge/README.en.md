# ChatGPT Cloud Collaboration · 0.1.1

[中文](README.md)

An optional cloud layer for the existing Codex router. The user-selected coordinator decomposes tasks and reviews results. Routine work remains local; bounded independent reviews can use ChatGPT Pro, and cloud execution can use Work. This is a Skill plus seven local MCP tools, not a host-enforced scheduler.

## Install

Requires Windows, PowerShell 7, Node.js 22+, a Codex CLI supporting `codex plugin`, an installed `playwright-core`, and a separately authenticated Chrome profile. Dependencies and browser credentials are not installed or copied automatically.

```powershell
git clone https://github.com/JingWang-Star996/codex-global-auto-routing.git
cd codex-global-auto-routing/plugins/codex-chatgpt-bridge
pwsh -NoProfile -File scripts/install.ps1
```

The public `.mcp.json` is intentionally empty. Run the installer first: it generates an absolute path for this checkout, registers a local marketplace and installs the plugin. `-PrepareOnly` generates the file without modifying Codex configuration or contacting a browser. Keep the checkout; rerun setup if moved. Do not commit the generated machine-specific `.mcp.json`. Tool discovery may require a new conversation or reload.

Use a dedicated Chrome profile with debugging bound only to `127.0.0.1:9334`, the adapter's fixed endpoint. Do not use the everyday profile or expose debugging beyond loopback. Sign in manually. Set `CHATGPT_BRIDGE_PLAYWRIGHT` to an installed `playwright-core/index.mjs`; otherwise the adapter only searches the Windows npm temporary cache. An existing CHR-005 setup can be reused; it is not supplied by this package.

## Use and boundaries

Invoke `$cloud-collaboration`, or ask the coordinator to delegate a useful independent perspective to the cloud and review the result. `mode=chat` selects GPT-6 with Pro intensity; `mode=work` selects GPT-6.1 Sol with the current web intensity. These choices were observed on the author's account, not guaranteed for every account. Work is not a Pro alias. Backend model and quota remain unknown.

Tools: `bridge_route`, `bridge_status`, `bridge_submit`, `bridge_poll`, `bridge_result`, `bridge_reconcile`, `bridge_close`. Routing suggestions are keyword rules; the coordinator performs semantic decomposition. The CLI exposes the same operations through `node src/server.mjs <operation> --input <json-file>` or `--json`.

Example packets deliberately have an empty `authorization`; fill the real task authorization and a stable unique ID before submission. This field records a coordinator assertion, not authenticated permission. Send only the minimum authorized context, never complete chat histories, credentials or unrelated files.

Same-ID submissions are idempotent; changed payloads conflict. An uncertain send is never resent automatically. Reconciliation requires one exact normalized prompt match in an already-open page. When the URL is missing, it examines user messages in open ChatGPT tabs; it does not search unopened history. Only one active cloud job is allowed.

Full replies remain on disk, with a maximum 1,500-character opening excerpt, path and hash returned to the coordinator. Truncated excerpts require further reading before acceptance. Completion needs the matching user turn, same-turn response, completion marker, complete UI state, visible response footer and no stop control. Read failures cannot prove completion. Cloud output is never executed automatically. Local close records review without cancelling remote work or deleting data.

State defaults to `.codex/state/chatgpt-bridge` under the user's home; override with `CHATGPT_BRIDGE_STATE`. A stale lock requires confirmation that its recorded process stopped before removal. Text/code only: no automatic attachment download. New chats do not prove account-memory isolation. Skills are not a cloud permission sandbox. Stop for login, challenges or access denial; no private ChatGPT APIs, token extraction or paid API fallback. Web UI changes can require maintenance; no unattended availability, cost reduction or enforced-routing guarantee.

Run `npm test` for offline checks without sending cloud requests. See [validation scope](docs/validation.md); private evidence is excluded from the public package.
