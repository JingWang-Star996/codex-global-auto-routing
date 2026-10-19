# ChatGPT 云端外脑 · 0.1.1

[English](README.en.md)

为现有 Codex 模型路由新增可选的云端协作入口。当前主模型负责拆解、授权和验收，常规任务仍走本地工位；独立复核或开放探索可交给 ChatGPT Pro，需要云端执行时可选择 Work。插件由 Skill 和7个本地 MCP 工具组成，不强制拦截所有任务。

## 安装

准备 Windows、PowerShell 7、Node.js 22+、支持 `codex plugin` 的 Codex CLI，以及已安装的 `playwright-core`。此插件不会自动安装依赖、创建登录态或复制浏览器资料。

```powershell
git clone https://github.com/JingWang-Star996/codex-global-auto-routing.git
cd codex-global-auto-routing/plugins/codex-chatgpt-bridge
pwsh -NoProfile -File scripts/install.ps1
```

公开的 `.mcp.json` 是空配置。安装脚本根据实际检出位置生成绝对路径，再注册本地市场并安装插件。先运行此脚本，不要直接将未准备的目录当成已接通的 MCP 插件。`-PrepareOnly` 只生成该文件，不改 Codex 配置或连接浏览器。保留源码目录；移动后重新运行安装器。生成的 `.mcp.json` 含本机路径，不要提交到公开仓库。

使用独立 Chrome profile，调试端口仅绑定 `127.0.0.1:9334`；这是适配器当前唯一允许的端点。不要使用日常 profile，不开放端口到局域网或公网。已有 CHR-005 环境可直接复用；其他机器需自行准备这个独立浏览器并由用户登录 ChatGPT。`CHATGPT_BRIDGE_PLAYWRIGHT` 可指定已安装的 `playwright-core/index.mjs` 绝对路径；未设置时仅尝试 Windows npm 临时缓存中的安装。

## 使用

加载插件后说：“按现有路由处理，需要独立视角的部分交给云端外脑，最后你验收。”也可调用 `$cloud-collaboration`。新安装可能需要新会话或刷新工具发现；安装成功不证明当前会话已经热加载。

| 入口 | 当前实现 |
| --- | --- |
| `mode=chat` | 网页选择 GPT-6 + Pro 强度 |
| `mode=work` | 网页选择 GPT-6.1 Sol，使用当前网页强度 |

这些标签来自作者本机的网页观察，不保证所有账号都有相同选项。Work不是Pro的别名；后台模型与额度均记为unknown。

工具：`bridge_route`、`bridge_status`、`bridge_submit`、`bridge_poll`、`bridge_result`、`bridge_reconcile`、`bridge_close`。route只是关键词建议，真正的语义拆解由主模型完成。

也可运行CLI：

```powershell
node src/server.mjs status
# 先编辑示例，填写本次真实授权、任务范围与唯一工作单元ID。
node src/server.mjs submit --input examples/pro-review.json
node src/server.mjs poll --json '{"work_unit_id":"example-pro-review-001"}'
node src/server.mjs result --json '{"work_unit_id":"example-pro-review-001","limit":1500}'
```

示例的authorization故意为空，直接提交会被拒绝。该字段仅记录协调者提供的授权依据，不是权限认证机制。仅发送用户授权范围内的必要材料，不附完整聊天、密钥或无关资料。

## 状态与数据

- 同ID同输入返回旧作业，改变输入报冲突。发送前持久记录；发送结果未知时不自动重发。
- reconcile只核对现有打开页面，完整任务包唯一匹配才恢复；没有URL时会读取打开的ChatGPT页的用户消息以寻找匹配，不检索未打开的历史。
- 每次新建对话，同时最多一个未关闭的活动作业。新对话不证明账号记忆隔离。
- 完整回复保存本地，回执只带最多1500字符的开头摘录、路径和SHA。截断时需回读全文，不能把摘录当成保真的语义摘要。
- 完成需要同一任务轮次、结束标记、网页complete状态、回复页脚可见且没有停止按钮。异常不会被当成完成。
- 主模型审阅后用close记录接受、驳回或放弃；close不终止远端任务、不删网页或本地数据。

状态默认位于用户主目录的 `.codex/state/chatgpt-bridge`，可用 `CHATGPT_BRIDGE_STATE` 指定。崩溃遗留锁不会自动删除；核对 `.lock/owner.json` 对应进程确已停止后再处理。只返回文本/代码，不自动下载附件或执行回复中的命令。

登录、验证码、权限拒绝或安全挑战时停止，不换通道绕过。没有私有ChatGPT接口、凭据提取或付费API回退。Skill约束不是云端权限沙箱。网页变化可能需要维护；不保证无人值守、成本下降或强制路由。

## 验证

运行 `npm test`。测试使用隔离本地夹具，不连接真实浏览器或发送消息。[验证范围](docs/validation.md)区分离线检查与作者本机的真实联调；公开包不包含私人聊天地址、授权记录、使用量、备份或部署路径。
