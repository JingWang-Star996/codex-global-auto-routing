# Codex 全局多模型路由 · R10

[中文](README.md) | [English](README.en.md)

[![离线测试](https://github.com/JingWang-Star996/codex-global-auto-routing/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/JingWang-Star996/codex-global-auto-routing/actions/workflows/offline-tests.yml)

面向 Windows Codex Desktop / CLI 的实验性个人配置包：保留用户选择的主模型，让协调者根据任务边界、风险和委派收益选择子 Agent 工位。它不是透明切换主模型的网关，也不是宿主级权限控制器。

## 这套规则做什么

| 工作类型 | 处理方式 |
| --- | --- |
| 计算、精确读回、范围清楚的小改动 | 主协调者优先用确定性工具直接完成 |
| 大量同构分类、抽取、去重 | `luna_batch_worker` |
| 跨文件语义追踪、代码与日志盘点 | `terra_explorer` |
| 常规多文件实现、调试、测试 | `terra_worker` |
| 安全、生产配置、并发等独立复核 | `sol_specialist` |
| Sol 根任务满足条件并获得具体授权后的单次只读求助 | `astra_specialist` |

主协调者始终由用户选择，负责授权、关键验收和最终答复。工位职责、任务包字段、失败分类、写入者交接与用量口径见 [完整策略](AGENTS.example.md)。

Spark 持续硬禁用：两个 Spark 名称只是兼容配置，模型保险映射到 Terra，禁止创建这些别名或调用 Spark provider；automatic 候选直接走 Terra，pinned Spark 请求拒绝。额度刷新不构成恢复授权。

## R10：受控向上求助

仅实际主模型为 `gpt-5.6-sol` 的根任务可以申请 Astra。默认先按正常路径工作；出现有证据的复杂推理卡点、未消除的证据冲突或明确的跨模型复核收益时，主动申请一次授权。启动时已有充分证据可以提前申请；本根已有具体预授权则不重复询问，也不强制调用。

拒绝、沉默、模糊回复均不是授权。用户可以撤销；已经预占的名额不释放，已发生的调用和用量不能承诺撤回。普通命令失败、额度、登录权限或需求歧义不触发升级。

每个根任务最多一次预占和调用，失败不重试。Astra 固定 `gpt-6-astra/high`，只做一个回合的分析或复核；不接管主协调者、不写入、不嵌套委派、不授权。详见 [R10 请求格式、核验与撤销流程](docs/upward-assist-r10.md)。

## 验证状态与限制

- R10 请求校验、一次性账本和消息组包有可运行的离线回归测试。
- 曾观察到 Sol 根任务实际创建 Astra 子任务，但首轮因任务包缺少预占成功摘要而被拒绝；消息组包已经修复，**修复后的正向运行验收仍未完成**。
- `upward_assist.py` 校验协调者提供的声明并维护一次性账本，不认证用户、根任务身份或真实模型，也不拦截绕开脚本的宿主调用。
- Hook 仅是 observer / diagnostic。安装、哈希一致、信任和 Hook 输出不证明宿主执行路由或阻止调用。
- profile 中的 `read-only` 是期望配置；实际 sandbox 必须从子任务运行元数据核验，父任务权限可能覆盖它。
- 字符数约束不是收费 Token 上限。本包不宣称已验证成本下降，也不代表用户业务目标完成。

本仓库不随附私人运行日志、用户授权、生产账本或历史部署备份；因此这里的离线测试不能替代这些宿主运行证据。

## 文件与准备

主要文件：`AGENTS.example.md`、`agents/*.toml`、`config.example.toml`、`hooks.example.json`、两个 `scripts/` 脚本、R10 文档和 `tests/`。英文部署镜像位于 `i18n/en/`，程序性名称、枚举和安全边界与中文版本保持一致。

准备 Windows PowerShell 5.1 或 PowerShell 7，以及 Python 3.11+（测试仅使用标准库）。模型和自定义工位是否可用，以当前宿主和账号为准；不可用时遵循策略中的降级与停止规则，不横向试模。

1. 审阅策略、profile、脚本，备份部署目标的现有配置。选定并固定本机 `CODEX_HOME`。
2. 中文部署使用根目录策略与 profiles；英文部署使用 `i18n/en/AGENTS.example.md` 和 `i18n/en/agents/`。只选择一种语言版本合并到用户级 `AGENTS.md` 和 Agent 配置，保留原有个人规则。把模板中的 `<CODEX_HOME>` 替换为该部署的实际绝对路径。
3. 审阅并部署对应语言的策略、profiles、R10 文档以及语言无关的 `scripts/upward_assist.py`。不要整文件覆盖已有 `config.toml`。按实际宿主支持的方式注册工位；确认角色已出现后才能使用，缺失时停止，不用通用角色代替。
4. 生产账本固定为 `<CODEX_HOME>/state/upward-assist-r10`。不要将测试账本复制进生产，也不要改目录或删除账本重新获得名额。部署这套配置本身不授权 Astra 调用。
5. 若需要 Hook，先运行下面的只读安装计划，再单独审核安装；已有 Hook 和 Token Hook 必须按摘要核验。安装器**只管理 Hook，不部署主策略或 Agent profiles**。

```powershell
# 从仓库目录运行；环境变量须已指向本次选定的用户级部署目录。
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-CodexRouter.ps1 -SourceRoot "$PWD" -TargetCodexHome "$env:CODEX_HOME" -PlanOnly
```

已有 `hooks.json` 时，按安装器要求传入已审阅的 `-ExpectedHooksSha256`；若保留已知 Token Hook pair，还需 `-ApprovedTokenSha256`。未知或重复 handler 会被拒绝，不能用覆盖绕过。省略 `-PlanOnly` 才会写入；发布此仓库不等于批准在任何机器部署。

部署后分别检查文件摘要、真实 child ID / model / effort / sandbox、文件变更和目标结果。新配置可能需要新会话或重启才能加载，旧会话自述不是加载证据。回滚前确认历史配置引用的脚本仍存在；不要删除活跃会话仍引用的内容寻址脚本。

## 离线验证

在仓库根目录运行，不需要 API key，不启动模型或真实子任务：

```powershell
python tests\test_upward_assist.py
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-RouterPolicyR10.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-R10AuthorizationTiming.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-BilingualParity.ps1
```

测试只使用隔离 fixtures / 测试输出，不应指向生产 `CODEX_HOME`。策略文字检查只能发现规则漂移，不能证明协调者真实遵守规则。

## 发布与许可

本次整理的是 R10 可移植配置和离线测试；本机源仓库及已部署配置不随发布修改。历史版本变化见 [中文](CHANGELOG.md) / [English](CHANGELOG.en.md)。

仓库公开可读，可依 GitHub 服务条款查看和 fork，但没有添加开源许可证，也不另行授予修改或再分发许可。不要提交生产状态、会话、授权引用、账户凭据或本机部署记录；忽略规则不能清除已有 Git 历史。
