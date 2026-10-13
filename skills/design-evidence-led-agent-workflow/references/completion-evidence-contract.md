# 完成状态与证据合同

## 合同与运行分开

工作合同定义目标、对象、门禁、权限、恢复和执行模型；运行记录定义本次工件、证据、审批、失败、交接和完成声明。运行必须绑定合同修订号与规范化合同 SHA-256，合同变化后旧运行不能替新合同背书。

## 使用独立 Claim，不使用一个万能状态

标准 Claim：

- `artifact_created`：工件真实存在，并有实例和摘要；
- `artifact_validated`：质量门禁通过，报告绑定当前工件摘要；
- `submission_accepted`：外部接口接受请求，只证明提交被接收；
- `destination_record_verified`：目标系统存在唯一且身份匹配的对象；
- `private_access_verified`：指定私密对象或收件范围实际可访问；
- `public_access_verified`：公开受众实际可访问；
- `outcome_verified`：业务效果另有现实指标证明。

这些 Claim 不是自动相邻的线性阶梯。`submission_accepted` 永远不能推出目标系统记录、私密访问、公开访问或业务效果。

运行状态只表示调度：

`not_started`、`in_progress`、`awaiting_approval`、`awaiting_external`、`paused`、`blocked`、`partial`、`complete`、`failed`、`cancelled`。

`complete` 只在所有目标 Claim、终态门禁、有效审批和证据齐全，且没有开放 F3/F4 失败时成立。

## 证据绑定

每条证据至少记录：

- 稳定 ID、证据类型、对象引用和支持的 Claim；
- `pass`、`fail` 或 `inconclusive`；
- 带时区的观察时间；
- 生产者、收集者和定位信息；
- 文件或对象摘要；
- 绑定的工件实例、远端对象、动作与合同修订；
- 是否含敏感信息及能否安全汇报。

文件证据使用当前 SHA-256。工件摘要变化后，旧验证、旧审批和旧提交证据标记为 `superseded`，不得继续放行。

## 证据类型

- `artifact_snapshot`：工件实例、定位与摘要；
- `validator_result`、`test_result`：确定性检查；
- `human_decision`：人工质量或风险判断；
- `operation_receipt`：外部接口接收动作；
- `destination_query`：目标系统唯一记录；
- `access_probe`：私密或公开访问；
- `metric_sample`：业务结果；
- `checkpoint`：可恢复状态；
- `log_excerpt`：受限的诊断证据。

## 外部副作用

发布、私密发送、付款、删除、敏感披露、外部承诺和权限变更必须：

- 由人类批准；
- 按运行或动作批准；
- 绑定合同版本、目标、动作和工件摘要；
- 批准未过期、未撤销，且工件未变化；
- 执行者不能批准自己的高风险动作。

外部结果不明且幂等性未知或不安全时，不得自动重试；先执行目标状态探测。无法确认是否已生效时记为 F4，并冻结相关写操作。

## 结构验收不等于视觉或外部验收

构建、OOXML、静态检查或结构审计通过，只支持 `artifact_validated` 中对应的技术部分。最终 DOCX 未逐页查看、真实客户端未访问、公开页未探测时，必须明确标为未运行，不得汇总成“全部通过”。
