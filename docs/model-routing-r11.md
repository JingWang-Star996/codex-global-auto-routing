# R11 模型路由与验收

主协调者默认直接完成任务，优先用脚本处理固定口径的计算和字段核对。用一个主笔追踪需要连续理解的材料，例如同一次会议中先提出建议、后来作出决定、又在结尾修改的事项。

决定分工后，按验收方式选工位：

- 要找某句原话、比对字段或按同一口径独立验算时，Luna 可从原始材料逐项交回证据。口径冲突可能影响结论时，将双方依据交回主笔。
- 要判断有没有把讨论写成定案时，主笔沿时间线核对提议、决定、变更和待定事项。需要第二意见时，请 `terra_explorer` 核查具体争点。重大冲突或高风险独立复核按下表选择 `sol_specialist`。
- 两个分支的输入互不依赖时可并行。复核成稿中的表述，应在成稿后针对疑点进行。用 `delegation_reason` 说明这次分工能解决什么问题。

四项真实任务的自动组均选择单人。另两次指定分工的质量、耗时和 Token 见[匿名对照记录](routing-benchmark-2026-11.md)。

| 工位 | 模型 / effort | 配置权限 |
| --- | --- | --- |
| luna_explorer | gpt-6-luna / low | read-only |
| luna_batch_worker | gpt-6-luna / low | read-only |
| luna_worker | gpt-6-luna / medium | workspace-write |
| terra_explorer | gpt-6.1-sol / medium | read-only |
| terra_worker | gpt-6.1-sol / medium | workspace-write |
| sol_specialist | gpt-6.1-sol / high | read-only |

默认子模型为 GPT-6 Luna / low。合并配置键时保留现有主模型、提供方、身份和其他个人规则。`config.example.toml` 和 profile 都只是部署候选；角色需要通过当前宿主支持的方式注册。

## 模型生效分层核验

分别记录请求的 model/effort、宿主注册映射、配置 profile、真实 child `turn_context`。固定角色可能忽略覆盖参数，文件更新也不证明旧会话已经加载新映射。首次采用只读任务核验父子 ID、实际角色、模型和 effort；不匹配则停止该路径，由主协调者接管，不换通用角色冒充目标模型。

未注册新 Luna 工位时，原 `luna_batch_worker` 只做冻结批处理及产物所需的只读读取与校验；普通检索、命令、测试与写入交主协调者。automatic 模型不可用后备仅能选已注册且映射符合目标的 Terra 工位。写入交接先确认前者终态、读回工件并递增 epoch；验收失败不能靠换模型掩盖。

运行核验器位于随附 [Skill](../skills/design-evidence-led-agent-workflow/SKILL.md) 的 `scripts/validate_agent_route.py`。它读取一个明确 profile 和一个明确 child transcript，要求父子 ID、请求模型、effort 与注册模型；多回合必须指定 turn ID。缺少元数据、身份冲突、旧注册模型、实际模型或 effort 不匹配均返回非零退出码。配置权限和实际 sandbox 单独报告；模型匹配不能推出宿主强制隔离。

## 证据与自动检查

实测曾出现“请求新模型、实际仍为旧角色模型”，以及抽取字段正确但汇总布尔值错误的情形。规范保存可复用的检查方法，私人原始会话和账号记录不进入此仓库。测试使用合成正反例；它们不是其他机器的运行验收。

可解析字段、数量与布尔结论由脚本重算；工位自报 `matches_expected`、`pass` 或 null 字段不是验收证据。当前版本不宣称完成全部新工位的宿主运行验收，也不宣称已证明成本下降。

## 授权边界

Spark provider、禁用兼容角色、Hook 和恢复机制不因 R11 开放。原 R10 公共包的 Astra 根模型资格仍为 `gpt-5.6-sol`，脚本、文档和一次性授权账本保持原样；普通工位迁到 6.1 不扩大这个通道。安装 Skill、修改配置、发布仓库都不构成 Astra 调用授权。

[English](model-routing-r11.en.md)
