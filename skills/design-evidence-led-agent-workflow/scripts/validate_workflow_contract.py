#!/usr/bin/env python3
"""Validate an evidence-led Agent workflow contract using only the standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CONTROL_MODELS = {"prompt", "loop", "workflow", "graph"}
EXECUTION_MODELS = {"single_agent", "multi_agent"}
RUN_STATUSES = {
    "not_started", "in_progress", "awaiting_approval", "awaiting_external",
    "paused", "blocked", "partial", "complete", "failed", "cancelled",
}
CLAIM_TYPES = {
    "artifact_created", "artifact_validated", "submission_accepted",
    "destination_record_verified", "private_access_verified",
    "public_access_verified", "outcome_verified",
}
CLAIM_STATUSES = {"asserted", "verified", "rejected", "inconclusive", "superseded"}
EVIDENCE_KINDS = {
    "artifact_snapshot", "validator_result", "test_result", "operation_receipt",
    "destination_query", "access_probe", "human_decision", "metric_sample",
    "checkpoint", "log_excerpt",
}
EVIDENCE_RESULTS = {"pass", "fail", "inconclusive"}
ACTION_CLASSES = {
    "read", "local_write", "external_write", "private_send", "public_release",
    "payment", "destructive_delete", "sensitive_disclosure",
    "external_commitment", "permission_change",
}
HIGH_RISK_ACTIONS = {
    "private_send", "public_release", "payment", "destructive_delete",
    "sensitive_disclosure", "external_commitment", "permission_change",
}
APPROVAL_STATUSES = {"not_requested", "pending", "approved", "denied", "expired", "revoked"}
GATE_RESULTS = {"pending", "pass", "fail", "waived"}
STEP_STATUSES = {"pending", "ready", "running", "waiting", "succeeded", "failed", "skipped", "cancelled"}
FAILURE_LEVELS = {"F0", "F1", "F2", "F3", "F4"}
FAILURE_STATUSES = {"open", "resolved", "waived"}
BOTTLENECKS = {
    "parallelizable_branches", "context_capacity",
    "permission_separation", "local_recovery",
}
BASELINE_STATUSES = {"planned", "completed", "waived"}
UPGRADE_STATUSES = {"not_proposed", "proposed", "approved", "tested", "adopted", "rejected"}

CLAIM_EVIDENCE_KINDS = {
    "artifact_created": {"artifact_snapshot"},
    "artifact_validated": {"validator_result", "test_result", "human_decision"},
    "submission_accepted": {"operation_receipt"},
    "destination_record_verified": {"destination_query"},
    "private_access_verified": {"access_probe"},
    "public_access_verified": {"access_probe"},
    "outcome_verified": {"metric_sample"},
}


def canonical_contract_sha256(contract: dict[str, Any]) -> str:
    payload = json.dumps(
        contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_document(document: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add(
        bucket: list[dict[str, Any]],
        code: str,
        path: str,
        message: str,
        refs: list[str] | None = None,
    ) -> None:
        item: dict[str, Any] = {"code": code, "path": path, "message": message}
        if refs:
            item["refs"] = refs
        bucket.append(item)

    def error(code: str, path: str, message: str, refs: list[str] | None = None) -> None:
        add(errors, code, path, message, refs)

    def warn(code: str, path: str, message: str, refs: list[str] | None = None) -> None:
        add(warnings, code, path, message, refs)

    if not isinstance(document, dict):
        error("E_SCHEMA", "$", "顶层必须是 JSON 对象")
        return _report(errors, warnings, {})

    if document.get("format") != "workflow-contract":
        error("E_SCHEMA", "$.format", "format 必须为 workflow-contract")
    if document.get("schema_version") != "1.0.0":
        error("E_SCHEMA", "$.schema_version", "schema_version 必须为 1.0.0")

    contract = _dict(document.get("contract"))
    run = _dict(document.get("run"))
    if not contract:
        error("E_SCHEMA", "$.contract", "缺少 contract 对象")
    if not run:
        error("E_SCHEMA", "$.run", "缺少 run 对象")
    if not contract or not run:
        return _report(errors, warnings, {})

    expected_contract_sha = canonical_contract_sha256(contract)

    collections: dict[str, list[dict[str, Any]]] = {
        "actors": [x for x in _list(contract.get("actors")) if isinstance(x, dict)],
        "objects": [x for x in _list(contract.get("objects")) if isinstance(x, dict)],
        "steps": [x for x in _list(contract.get("steps")) if isinstance(x, dict)],
        "gates": [x for x in _list(contract.get("gates")) if isinstance(x, dict)],
        "permissions": [
            x for x in _list(_dict(contract.get("permissions")).get("rules"))
            if isinstance(x, dict)
        ],
        "recovery_plans": [
            x for x in _list(contract.get("recovery_plans")) if isinstance(x, dict)
        ],
        "object_instances": [
            x for x in _list(run.get("object_instances")) if isinstance(x, dict)
        ],
        "step_records": [
            x for x in _list(run.get("step_records")) if isinstance(x, dict)
        ],
        "claims": [x for x in _list(run.get("claims")) if isinstance(x, dict)],
        "evidence": [x for x in _list(run.get("evidence")) if isinstance(x, dict)],
        "approvals": [x for x in _list(run.get("approvals")) if isinstance(x, dict)],
        "handoffs": [x for x in _list(run.get("handoffs")) if isinstance(x, dict)],
        "failures": [x for x in _list(run.get("failures")) if isinstance(x, dict)],
        "gate_results": [
            x for x in _list(run.get("gate_results")) if isinstance(x, dict)
        ],
    }

    indexes: dict[str, dict[str, dict[str, Any]]] = {}
    global_ids: dict[str, str] = {}
    for name, items in collections.items():
        index: dict[str, dict[str, Any]] = {}
        for offset, item in enumerate(items):
            path = f"$.{name}[{offset}]"
            item_id = item.get("id")
            if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id):
                error("E_SCHEMA", f"{path}.id", "ID 必须匹配 ^[a-z][a-z0-9._-]{0,63}$")
                continue
            if item_id in global_ids:
                error(
                    "E_SCHEMA",
                    f"{path}.id",
                    f"ID 与 {global_ids[item_id]} 重复",
                    [item_id],
                )
            else:
                global_ids[item_id] = path
            index[item_id] = item
        indexes[name] = index

    for top_id_path, top_id in (("$.contract.id", contract.get("id")), ("$.run.id", run.get("id"))):
        if not isinstance(top_id, str) or not ID_RE.fullmatch(top_id):
            error("E_SCHEMA", top_id_path, "ID 必须匹配 ^[a-z][a-z0-9._-]{0,63}$")

    revision = contract.get("revision")
    if not isinstance(revision, int) or revision < 1:
        error("E_SCHEMA", "$.contract.revision", "revision 必须是大于 0 的整数")
    if run.get("contract_revision") != revision:
        error("E_EVIDENCE_BINDING", "$.run.contract_revision", "运行记录未绑定当前合同修订")

    actual_contract_sha = run.get("contract_sha256")
    if not actual_contract_sha:
        if run.get("status") == "not_started":
            warn(
                "W_CONTRACT_DIGEST_MISSING",
                "$.run.contract_sha256",
                f"复制模板后应写入规范化合同摘要 {expected_contract_sha}",
            )
        else:
            error("E_DIGEST", "$.run.contract_sha256", "运行开始后必须绑定合同 SHA-256")
    elif not isinstance(actual_contract_sha, str) or not SHA256_RE.fullmatch(actual_contract_sha):
        error("E_DIGEST", "$.run.contract_sha256", "合同摘要必须是 64 位小写 SHA-256")
    elif actual_contract_sha != expected_contract_sha:
        error(
            "E_EVIDENCE_BINDING",
            "$.run.contract_sha256",
            "合同摘要与当前 contract 对象不一致",
        )

    run_status = run.get("status")
    if run_status not in RUN_STATUSES:
        error("E_ENUM", "$.run.status", f"未知运行状态：{run_status}")

    actors = indexes["actors"]
    objects = indexes["objects"]
    steps = indexes["steps"]
    gates = indexes["gates"]
    permission_rules = indexes["permissions"]
    recovery_plans = indexes["recovery_plans"]
    object_instances = indexes["object_instances"]
    claims = indexes["claims"]
    evidence = indexes["evidence"]
    approvals = indexes["approvals"]

    completion_writers = [
        actor_id for actor_id, actor in actors.items()
        if "completion_writer" in _list(actor.get("roles"))
    ]
    if len(completion_writers) != 1:
        error("E_FINAL_AUTHORITY", "$.contract.actors", "必须且只能有一个 completion_writer")

    success = _dict(contract.get("success"))
    authority_ref = success.get("completion_authority_ref")
    if authority_ref not in actors:
        error("E_REF", "$.contract.success.completion_authority_ref", "完成负责人不存在")
    elif completion_writers and authority_ref != completion_writers[0]:
        error("E_FINAL_AUTHORITY", "$.contract.success", "完成负责人必须是唯一 completion_writer")

    objective = _dict(contract.get("objective"))
    if not isinstance(objective.get("statement"), str) or not objective.get("statement", "").strip():
        error("E_SCHEMA", "$.contract.objective.statement", "必须写出可验收目标")
    if not isinstance(objective.get("in_scope"), list) or not isinstance(objective.get("out_of_scope"), list):
        error("E_SCHEMA", "$.contract.objective", "in_scope 与 out_of_scope 必须是数组")

    _validate_control_model(contract, error, warn)

    for index, target in enumerate(_list(success.get("targets"))):
        path = f"$.contract.success.targets[{index}]"
        if not isinstance(target, dict):
            error("E_SCHEMA", path, "目标必须是对象")
            continue
        if target.get("object_ref") not in objects:
            error("E_REF", f"{path}.object_ref", "目标对象不存在")
        for claim_type in _list(target.get("required_claims")):
            if claim_type not in CLAIM_TYPES:
                error("E_ENUM", f"{path}.required_claims", f"未知 Claim：{claim_type}")

    for claim_type in _list(success.get("forbidden_claims")):
        if claim_type not in CLAIM_TYPES:
            error("E_ENUM", "$.contract.success.forbidden_claims", f"未知 Claim：{claim_type}")
    for gate_ref in _list(success.get("terminal_gate_refs")):
        if gate_ref not in gates:
            error("E_REF", "$.contract.success.terminal_gate_refs", f"门禁不存在：{gate_ref}")

    for object_id, obj in objects.items():
        if obj.get("write_policy") not in {"single_writer", "append_only", "merge_required"}:
            error("E_ENUM", f"$.objects.{object_id}.write_policy", "未知写入策略")
        if obj.get("digest_required") not in {"sha256", "none"}:
            error("E_ENUM", f"$.objects.{object_id}.digest_required", "digest_required 必须为 sha256 或 none")

    writers_by_object: dict[str, list[str]] = {object_id: [] for object_id in objects}
    high_risk_steps: dict[str, str] = {}
    for step_id, step in steps.items():
        step_path = f"$.contract.steps[{step_id}]"
        if step.get("executor_ref") not in actors:
            error("E_REF", f"{step_path}.executor_ref", "执行者不存在")
        for dep in _list(step.get("depends_on")):
            if dep not in steps:
                error("E_REF", f"{step_path}.depends_on", f"依赖步骤不存在：{dep}")
        for field in ("allowed_reads", "allowed_writes", "outputs"):
            for object_ref in _list(step.get(field)):
                if object_ref not in objects:
                    error("E_REF", f"{step_path}.{field}", f"对象不存在：{object_ref}")
                if field == "allowed_writes" and object_ref in writers_by_object:
                    writers_by_object[object_ref].append(step_id)
        if not set(_list(step.get("outputs"))).issubset(set(_list(step.get("allowed_writes")))):
            error("E_COLLABORATION", f"{step_path}.outputs", "输出对象必须包含在 allowed_writes 中")
        for field in ("entry_gate_refs", "exit_gate_refs"):
            for gate_ref in _list(step.get(field)):
                if gate_ref not in gates:
                    error("E_REF", f"{step_path}.{field}", f"门禁不存在：{gate_ref}")
        for claim_type in _list(step.get("emits_claims")):
            if claim_type not in CLAIM_TYPES:
                error("E_ENUM", f"{step_path}.emits_claims", f"未知 Claim：{claim_type}")
        recovery_ref = step.get("recovery_ref")
        if recovery_ref not in recovery_plans:
            error("E_RECOVERY", f"{step_path}.recovery_ref", "步骤必须引用恢复计划")
        side_effect = _dict(step.get("side_effect"))
        action_class = side_effect.get("action_class")
        if action_class not in ACTION_CLASSES:
            error("E_ENUM", f"{step_path}.side_effect.action_class", f"未知动作类型：{action_class}")
        if action_class in HIGH_RISK_ACTIONS:
            high_risk_steps[step_id] = action_class
            matching = [
                rule for rule in permission_rules.values()
                if rule.get("action_class") == action_class
                and step.get("executor_ref") in _list(rule.get("executor_refs"))
                and set(_list(step.get("outputs"))).issubset(set(_list(rule.get("target_refs"))))
            ]
            if not matching:
                error("E_AUTHORIZATION", step_path, "高风险步骤没有匹配的权限规则")
        idempotency = side_effect.get("idempotency")
        if idempotency in {"unknown", "unsafe"} and recovery_ref in recovery_plans:
            plan = recovery_plans[recovery_ref]
            if plan.get("retry_mode") not in {"manual", "forbidden", "probe_first"}:
                error("E_RECOVERY", step_path, "幂等性未知或不安全时不得自动重试")
            if plan.get("retry_mode") == "probe_first" and not plan.get("outcome_probe_step_ref"):
                error("E_RECOVERY", step_path, "probe_first 必须指定 outcome_probe_step_ref")

    for object_id, writers in writers_by_object.items():
        policy = objects[object_id].get("write_policy")
        if policy == "single_writer" and len(set(writers)) > 1:
            error(
                "E_COLLABORATION",
                f"$.contract.objects[{object_id}]",
                "single_writer 对象被多个步骤写入",
                sorted(set(writers)),
            )
        if policy == "merge_required" and len(set(writers)) > 1:
            merge_ref = objects[object_id].get("merge_step_ref")
            if merge_ref not in steps:
                error("E_COLLABORATION", f"$.contract.objects[{object_id}]", "多写者对象缺少有效 merge_step_ref")

    for gate_id, gate in gates.items():
        gate_path = f"$.contract.gates[{gate_id}]"
        requires = _dict(gate.get("requires"))
        for claim_type in _list(requires.get("claim_types")):
            if claim_type not in CLAIM_TYPES:
                error("E_ENUM", f"{gate_path}.requires.claim_types", f"未知 Claim：{claim_type}")
        for permission_ref in _list(requires.get("approval_rule_refs")):
            if permission_ref not in permission_rules:
                error("E_REF", f"{gate_path}.requires.approval_rule_refs", f"权限规则不存在：{permission_ref}")
        for gate_ref in _list(requires.get("gate_refs")):
            if gate_ref not in gates:
                error("E_REF", f"{gate_path}.requires.gate_refs", f"门禁不存在：{gate_ref}")

    for rule_id, rule in permission_rules.items():
        rule_path = f"$.contract.permissions.rules[{rule_id}]"
        action_class = rule.get("action_class")
        if action_class not in ACTION_CLASSES:
            error("E_ENUM", f"{rule_path}.action_class", "未知动作类型")
        for actor_ref in _list(rule.get("executor_refs")):
            if actor_ref not in actors:
                error("E_REF", f"{rule_path}.executor_refs", f"执行者不存在：{actor_ref}")
        for object_ref in _list(rule.get("target_refs")):
            if object_ref not in objects:
                error("E_REF", f"{rule_path}.target_refs", f"目标对象不存在：{object_ref}")
        authorities = _list(rule.get("approval_authority_refs"))
        for actor_ref in authorities:
            if actor_ref not in actors:
                error("E_REF", f"{rule_path}.approval_authority_refs", f"审批者不存在：{actor_ref}")
            elif actors[actor_ref].get("kind") != "human":
                error("E_AUTHORIZATION", f"{rule_path}.approval_authority_refs", "高风险动作必须由人类审批")
        if action_class in HIGH_RISK_ACTIONS:
            if rule.get("approval_mode") not in {"per_run", "per_action"}:
                error("E_AUTHORIZATION", f"{rule_path}.approval_mode", "高风险动作必须按运行或动作审批")
            if not authorities:
                error("E_AUTHORIZATION", f"{rule_path}.approval_authority_refs", "缺少人类审批者")

    for plan_id, plan in recovery_plans.items():
        plan_path = f"$.contract.recovery_plans[{plan_id}]"
        if plan.get("recovery_owner_ref") not in actors:
            error("E_REF", f"{plan_path}.recovery_owner_ref", "恢复负责人不存在")
        for field in ("resume_from_step_ref", "outcome_probe_step_ref", "rollback_step_ref"):
            ref = plan.get(field)
            if ref is not None and ref not in steps:
                error("E_REF", f"{plan_path}.{field}", f"步骤不存在：{ref}")
        if plan.get("retry_mode") not in {"safe", "manual", "forbidden", "probe_first"}:
            error("E_ENUM", f"{plan_path}.retry_mode", "未知重试模式")
        if not isinstance(plan.get("max_attempts"), int) or plan.get("max_attempts") < 0:
            error("E_SCHEMA", f"{plan_path}.max_attempts", "max_attempts 必须是非负整数")

    _validate_execution_model(contract, run, indexes, error, warn)
    _validate_run(
        contract, run, indexes, high_risk_steps, expected_contract_sha, error, warn
    )

    verified_claim_types = sorted({
        claim.get("type") for claim in collections["claims"]
        if claim.get("status") == "verified"
    })
    gate_passes = {
        result.get("gate_ref") for result in collections["gate_results"]
        if result.get("result") == "pass"
    }
    next_blocking_gates = sorted(
        set(_list(success.get("terminal_gate_refs"))) - gate_passes
    )
    safe_resume_steps = sorted({
        plan.get("resume_from_step_ref") for plan in collections["recovery_plans"]
        if plan.get("resume_from_step_ref")
    })
    derived = {
        "contract_sha256": expected_contract_sha,
        "verified_claims": verified_claim_types,
        "next_blocking_gates": next_blocking_gates,
        "safe_resume_steps": safe_resume_steps,
    }
    return _report(errors, warnings, derived)


def _validate_control_model(contract: dict[str, Any], error, warn) -> None:
    model = _dict(contract.get("control_model"))
    selected = model.get("selected")
    if selected not in CONTROL_MODELS:
        error("E_ENUM", "$.contract.control_model.selected", "控制形状必须为 prompt、loop、workflow 或 graph")
        return
    if not isinstance(model.get("reason"), str) or not model.get("reason", "").strip():
        error("E_SCHEMA", "$.contract.control_model.reason", "必须写出架构选择理由")
    signals = _dict(model.get("signals"))
    names = (
        "requires_iteration", "fixed_sequence", "dynamic_branching",
        "durable_state", "permission_handoffs", "partial_recovery",
    )
    for name in names:
        if not isinstance(signals.get(name), bool):
            error("E_SCHEMA", f"$.contract.control_model.signals.{name}", "架构信号必须是布尔值")
    if selected == "prompt" and any(signals.get(name) for name in names if name != "fixed_sequence"):
        error("E_ARCHITECTURE", "$.contract.control_model", "Prompt 无法承担已声明的循环、状态、权限或恢复需求")
    if selected == "loop" and any(
        signals.get(name) for name in ("dynamic_branching", "durable_state", "permission_handoffs", "partial_recovery")
    ):
        warn("W_ARCHITECTURE_UNDERFIT", "$.contract.control_model", "Loop 可能不足，应评估 Graph")
    if selected == "workflow" and any(
        signals.get(name) for name in ("dynamic_branching", "durable_state", "partial_recovery")
    ):
        warn("W_ARCHITECTURE_UNDERFIT", "$.contract.control_model", "固定 Workflow 可能不足，应评估 Graph")
    if selected == "graph" and not any(
        signals.get(name) for name in ("dynamic_branching", "durable_state", "permission_handoffs", "partial_recovery")
    ):
        warn("W_ARCHITECTURE_OVERFIT", "$.contract.control_model", "没有发现必须使用 Graph 的信号")


def _validate_execution_model(contract, run, indexes, error, warn) -> None:
    model = _dict(contract.get("execution_model"))
    selected = model.get("selected")
    if selected not in EXECUTION_MODELS:
        error("E_ENUM", "$.contract.execution_model.selected", "执行模式必须为 single_agent 或 multi_agent")
        return
    baseline = _dict(model.get("single_agent_baseline"))
    baseline_status = baseline.get("status")
    if baseline_status not in BASELINE_STATUSES:
        error("E_ENUM", "$.contract.execution_model.single_agent_baseline.status", "未知基线状态")
    if baseline.get("agent_profile_ref") not in indexes["actors"]:
        error("E_REF", "$.contract.execution_model.single_agent_baseline.agent_profile_ref", "基线 Agent 不存在")
    for gate_ref in _list(baseline.get("acceptance_gate_refs")):
        if gate_ref not in indexes["gates"]:
            error("E_REF", "$.contract.execution_model.single_agent_baseline.acceptance_gate_refs", f"门禁不存在：{gate_ref}")
    if baseline_status == "completed":
        digest = _dict(baseline.get("task_set_digest"))
        if digest.get("algorithm") != "sha256" or not SHA256_RE.fullmatch(str(digest.get("value", ""))):
            error("E_DIGEST", "$.contract.execution_model.single_agent_baseline.task_set_digest", "已完成基线必须绑定任务集 SHA-256")
        if not _list(baseline.get("run_refs")):
            error("E_BASELINE", "$.contract.execution_model.single_agent_baseline.run_refs", "已完成基线必须引用运行")
    stable_rule = _dict(baseline.get("stable_failure_rule"))
    if not isinstance(stable_rule.get("min_occurrences"), int) or stable_rule.get("min_occurrences", 0) < 2:
        error("E_BASELINE", "$.contract.execution_model.single_agent_baseline.stable_failure_rule", "稳定失败至少要求重复 2 次")

    upgrade = _dict(model.get("multi_agent_upgrade"))
    status = upgrade.get("status")
    if status not in UPGRADE_STATUSES:
        error("E_ENUM", "$.contract.execution_model.multi_agent_upgrade.status", "未知多体升级状态")
        return
    active_upgrade = selected == "multi_agent" or status in {"approved", "tested", "adopted"}
    if status == "adopted" and selected != "multi_agent":
        error("E_MULTI_AGENT_CASE", "$.contract.execution_model", "已采用多 Agent 时 selected 必须为 multi_agent")
    if not active_upgrade:
        return
    if baseline_status not in {"completed", "waived"}:
        error("E_BASELINE", "$.contract.execution_model.single_agent_baseline", "多 Agent 必须有已完成基线或有效豁免")
    if baseline_status == "waived":
        waiver_ref = baseline.get("waiver_ref")
        approval = indexes["approvals"].get(waiver_ref)
        if not approval or approval.get("status") != "approved":
            error("E_BASELINE", "$.contract.execution_model.single_agent_baseline.waiver_ref", "基线豁免必须引用有效人工批准")
    bottlenecks = _list(upgrade.get("bottlenecks"))
    if not bottlenecks or any(item not in BOTTLENECKS for item in bottlenecks):
        error("E_MULTI_AGENT_CASE", "$.contract.execution_model.multi_agent_upgrade.bottlenecks", "必须声明受支持的具体瓶颈")
    if bottlenecks != ["permission_separation"] and not _list(upgrade.get("failure_refs")):
        error("E_MULTI_AGENT_CASE", "$.contract.execution_model.multi_agent_upgrade.failure_refs", "除纯权限隔离外，多体升级必须引用稳定失败")
    hypothesis = _dict(upgrade.get("hypothesis"))
    required_hypothesis = {"condition", "stable_failure_code", "change", "measure", "direction", "minimum_delta"}
    if not required_hypothesis.issubset(hypothesis):
        error("E_MULTI_AGENT_CASE", "$.contract.execution_model.multi_agent_upgrade.hypothesis", "缺少可证伪升级假设")
    if not _dict(upgrade.get("topology")):
        error("E_MULTI_AGENT_CASE", "$.contract.execution_model.multi_agent_upgrade.topology", "缺少最小多体拓扑")
    agent_count = sum(1 for actor in indexes["actors"].values() if actor.get("kind") == "agent")
    if agent_count < 2:
        error("E_MULTI_AGENT_CASE", "$.contract.actors", "多 Agent 模式至少需要两个 Agent actor")
    if status in {"tested", "adopted"} and not _dict(upgrade.get("comparison")):
        error("E_MULTI_AGENT_CASE", "$.contract.execution_model.multi_agent_upgrade.comparison", "测试或采用前必须保存同任务集对照")
    if not _list(upgrade.get("overhead_budget")):
        warn("W_REVIEW_CAPACITY", "$.contract.execution_model.multi_agent_upgrade.overhead_budget", "尚未记录协调、合并、验证和人审成本")


def _validate_run(contract, run, indexes, high_risk_steps, contract_sha, error, warn) -> None:
    objects = indexes["objects"]
    object_instances = indexes["object_instances"]
    claims = indexes["claims"]
    evidence = indexes["evidence"]
    approvals = indexes["approvals"]
    actors = indexes["actors"]
    permission_rules = indexes["permissions"]

    current_instances: dict[str, list[str]] = {}
    for instance_id, instance in object_instances.items():
        path = f"$.run.object_instances[{instance_id}]"
        object_ref = instance.get("object_ref")
        if object_ref not in objects:
            error("E_REF", f"{path}.object_ref", "对象实例引用不存在")
        if instance.get("status") not in {"current", "superseded"}:
            error("E_ENUM", f"{path}.status", "对象实例状态必须为 current 或 superseded")
        digest = _dict(instance.get("digest"))
        if digest.get("algorithm") != "sha256" or not SHA256_RE.fullmatch(str(digest.get("value", ""))):
            error("E_DIGEST", f"{path}.digest", "对象实例必须绑定 64 位小写 SHA-256")
        if instance.get("status") == "current" and object_ref in objects:
            current_instances.setdefault(object_ref, []).append(instance_id)
    for object_ref, ids in current_instances.items():
        if len(ids) > 1:
            error("E_EVIDENCE_BINDING", "$.run.object_instances", f"对象 {object_ref} 同时存在多个 current 实例", ids)

    for evidence_id, item in evidence.items():
        path = f"$.run.evidence[{evidence_id}]"
        if item.get("kind") not in EVIDENCE_KINDS:
            error("E_ENUM", f"{path}.kind", "未知证据类型")
        if item.get("result") not in EVIDENCE_RESULTS:
            error("E_ENUM", f"{path}.result", "未知证据结果")
        if not _is_timestamp(item.get("observed_at")):
            error("E_SCHEMA", f"{path}.observed_at", "证据时间必须包含时区")
        collector_ref = item.get("collector_ref")
        if collector_ref not in actors:
            error("E_REF", f"{path}.collector_ref", "证据收集者不存在")
        for claim_ref in _list(item.get("supports_claim_refs")):
            if claim_ref not in claims:
                error("E_REF", f"{path}.supports_claim_refs", f"Claim 不存在：{claim_ref}")
        digest = _dict(item.get("digest"))
        if digest and (
            digest.get("algorithm") != "sha256"
            or not SHA256_RE.fullmatch(str(digest.get("value", "")))
        ):
            error("E_DIGEST", f"{path}.digest", "证据摘要必须是 64 位小写 SHA-256")
        binding = _dict(item.get("binding"))
        instance_ref = binding.get("object_instance_ref")
        if instance_ref:
            instance = object_instances.get(instance_ref)
            if not instance:
                error("E_REF", f"{path}.binding.object_instance_ref", "绑定的对象实例不存在")
            else:
                expected = _dict(instance.get("digest")).get("value")
                if instance.get("status") != "current":
                    error("E_EVIDENCE_BINDING", path, "证据绑定了已被替代的工件")
                if binding.get("object_sha256") != expected:
                    error("E_EVIDENCE_BINDING", f"{path}.binding.object_sha256", "证据未绑定当前工件摘要")

    for claim_id, claim in claims.items():
        path = f"$.run.claims[{claim_id}]"
        claim_type = claim.get("type")
        status = claim.get("status")
        if claim_type not in CLAIM_TYPES:
            error("E_ENUM", f"{path}.type", "未知 Claim")
        if status not in CLAIM_STATUSES:
            error("E_ENUM", f"{path}.status", "未知 Claim 状态")
        subject_ref = claim.get("subject_ref")
        if subject_ref not in object_instances:
            error("E_REF", f"{path}.subject_ref", "Claim 必须绑定对象实例")
        elif status == "verified" and object_instances[subject_ref].get("status") != "current":
            error("E_EVIDENCE_BINDING", path, "已验证 Claim 绑定了被替代工件")
        evidence_refs = _list(claim.get("evidence_refs"))
        if status == "verified":
            if not evidence_refs:
                error("E_COMPLETION_GAP", f"{path}.evidence_refs", "已验证 Claim 缺少证据")
            kinds: set[str] = set()
            for ref in evidence_refs:
                item = evidence.get(ref)
                if not item:
                    error("E_REF", f"{path}.evidence_refs", f"证据不存在：{ref}")
                    continue
                kinds.add(str(item.get("kind")))
                if item.get("result") != "pass":
                    error("E_COMPLETION_GAP", path, "已验证 Claim 引用了未通过证据", [ref])
                if claim_id not in _list(item.get("supports_claim_refs")):
                    error("E_EVIDENCE_BINDING", path, "证据没有反向绑定该 Claim", [ref])
            required_kinds = CLAIM_EVIDENCE_KINDS.get(claim_type, set())
            if kinds.isdisjoint(required_kinds):
                error("E_COMPLETION_GAP", path, f"{claim_type} 缺少匹配类型的证据")
            if claim_type in {"private_access_verified", "public_access_verified"}:
                audience = "private" if claim_type.startswith("private") else "public"
                probes = [evidence.get(ref, {}) for ref in evidence_refs if evidence.get(ref, {}).get("kind") == "access_probe"]
                if not any(
                    _dict(probe.get("details")).get("audience_scope") == audience
                    and _dict(probe.get("details")).get("accessible") is True
                    and _dict(probe.get("details")).get("identity_match") is True
                    for probe in probes
                ):
                    error("E_COMPLETION_GAP", path, f"{claim_type} 缺少受众、可访问和身份匹配证据")
            if claim_type == "destination_record_verified":
                queries = [evidence.get(ref, {}) for ref in evidence_refs if evidence.get(ref, {}).get("kind") == "destination_query"]
                if not any(
                    _dict(query.get("details")).get("identity_match") is True
                    and _dict(query.get("details")).get("unique") is True
                    for query in queries
                ):
                    error("E_COMPLETION_GAP", path, "目标记录 Claim 缺少 identity_match=true 与 unique=true")

    for approval_id, approval in approvals.items():
        path = f"$.run.approvals[{approval_id}]"
        if approval.get("status") not in APPROVAL_STATUSES:
            error("E_ENUM", f"{path}.status", "未知审批状态")
        rule_ref = approval.get("permission_rule_ref")
        rule = permission_rules.get(rule_ref)
        if not rule:
            error("E_REF", f"{path}.permission_rule_ref", "权限规则不存在")
            continue
        if approval.get("contract_revision") != contract.get("revision"):
            error("E_AUTHORIZATION", path, "审批未绑定当前合同修订")
        executor_ref = approval.get("executor_ref")
        authority_ref = approval.get("authority_ref")
        if executor_ref not in actors or authority_ref not in actors:
            error("E_REF", path, "审批执行者或批准者不存在")
        elif actors[authority_ref].get("kind") != "human" or authority_ref == executor_ref:
            error("E_AUTHORIZATION", path, "高风险动作必须由非执行者的人类批准")
        if approval.get("status") == "approved" and not _is_timestamp(approval.get("approved_at")):
            error("E_SCHEMA", f"{path}.approved_at", "已批准记录必须有带时区时间")
        for binding in _list(approval.get("object_bindings")):
            if not isinstance(binding, dict):
                error("E_SCHEMA", f"{path}.object_bindings", "对象绑定必须是对象")
                continue
            instance_ref = binding.get("object_instance_ref")
            instance = object_instances.get(instance_ref)
            if not instance:
                error("E_REF", f"{path}.object_bindings", "审批绑定的对象实例不存在")
            elif instance.get("status") != "current" or binding.get("sha256") != _dict(instance.get("digest")).get("value"):
                error("E_AUTHORIZATION", f"{path}.object_bindings", "审批未绑定当前工件摘要")

    for record_id, record in indexes["step_records"].items():
        path = f"$.run.step_records[{record_id}]"
        step_ref = record.get("step_ref")
        if step_ref not in indexes["steps"]:
            error("E_REF", f"{path}.step_ref", "步骤记录引用不存在")
        if record.get("status") not in STEP_STATUSES:
            error("E_ENUM", f"{path}.status", "未知步骤状态")
        if record.get("status") == "succeeded" and step_ref in high_risk_steps:
            action_class = high_risk_steps[step_ref]
            step = indexes["steps"][step_ref]
            matching_rule_ids = [
                rule_id for rule_id, rule in permission_rules.items()
                if rule.get("action_class") == action_class
                and step.get("executor_ref") in _list(rule.get("executor_refs"))
            ]
            valid_approval = any(
                approval.get("permission_rule_ref") in matching_rule_ids
                and approval.get("status") == "approved"
                and approval.get("contract_revision") == contract.get("revision")
                for approval in approvals.values()
            )
            if not valid_approval:
                error("E_AUTHORIZATION", path, "高风险步骤已成功，但没有有效人工批准")

    for handoff_id, handoff in indexes["handoffs"].items():
        path = f"$.run.handoffs[{handoff_id}]"
        if handoff.get("from_ref") not in actors or handoff.get("to_ref") not in actors:
            error("E_REF", path, "交接双方必须是已声明 actor")
        payload_fields = ("artifact_refs", "evidence_refs", "decision_refs", "state_change_refs")
        if not any(_list(handoff.get(field)) for field in payload_fields):
            error("E_COLLABORATION", path, "交接必须新增工件、证据、决定或状态变化")

    open_severe_failures: list[str] = []
    for failure_id, failure in indexes["failures"].items():
        path = f"$.run.failures[{failure_id}]"
        if failure.get("level") not in FAILURE_LEVELS:
            error("E_ENUM", f"{path}.level", "未知失败级别")
        if failure.get("status") not in FAILURE_STATUSES:
            error("E_ENUM", f"{path}.status", "未知失败状态")
        if failure.get("level") in {"F3", "F4"} and failure.get("status") == "open":
            open_severe_failures.append(failure_id)

    gate_passes: set[str] = set()
    for result_id, result in indexes["gate_results"].items():
        path = f"$.run.gate_results[{result_id}]"
        gate_ref = result.get("gate_ref")
        if gate_ref not in indexes["gates"]:
            error("E_REF", f"{path}.gate_ref", "门禁不存在")
        if result.get("result") not in GATE_RESULTS:
            error("E_ENUM", f"{path}.result", "未知门禁结果")
        if result.get("result") == "pass":
            gate_passes.add(gate_ref)
        for ref in _list(result.get("evidence_refs")):
            if ref not in evidence:
                error("E_REF", f"{path}.evidence_refs", f"证据不存在：{ref}")

    success = _dict(contract.get("success"))
    forbidden = set(_list(success.get("forbidden_claims")))
    active_forbidden = [
        claim_id for claim_id, claim in claims.items()
        if claim.get("type") in forbidden
        and claim.get("status") not in {"rejected", "superseded"}
    ]
    if active_forbidden:
        error("E_FORBIDDEN_CLAIM", "$.run.claims", "运行记录出现合同禁止的 Claim", active_forbidden)

    completion = _dict(run.get("completion"))
    declared = completion.get("declared") is True
    if run.get("status") == "complete" and not declared:
        error("E_COMPLETION_GAP", "$.run.completion", "运行状态为 complete，但未声明完成")
    if declared and run.get("status") not in {"complete", "partial"}:
        error("E_COMPLETION_GAP", "$.run.status", "已声明完成时运行状态必须为 complete 或 partial")
    if run.get("status") == "partial":
        if success.get("allow_partial") is not True or not _list(completion.get("partial_object_refs")):
            error("E_COMPLETION_GAP", "$.run.completion", "partial 必须获合同允许并列出部分完成对象")
    if declared or run.get("status") == "complete":
        authority = success.get("completion_authority_ref")
        if completion.get("declared_by") != authority:
            error("E_FINAL_AUTHORITY", "$.run.completion.declared_by", "只有完成负责人可以声明完成")
        if not _is_timestamp(completion.get("declared_at")):
            error("E_SCHEMA", "$.run.completion.declared_at", "完成时间必须包含时区")
        if open_severe_failures:
            error("E_COMPLETION_GAP", "$.run.failures", "存在开放的 F3/F4 失败", open_severe_failures)
        missing_gates = set(_list(success.get("terminal_gate_refs"))) - gate_passes
        if missing_gates:
            error("E_COMPLETION_GAP", "$.run.gate_results", "终态门禁尚未全部通过", sorted(missing_gates))
        for target in _list(success.get("targets")):
            if not isinstance(target, dict):
                continue
            object_ref = target.get("object_ref")
            current_ids = current_instances.get(object_ref, [])
            if not current_ids:
                error("E_COMPLETION_GAP", "$.run.object_instances", f"目标 {object_ref} 没有 current 工件实例")
                continue
            verified_types = {
                claim.get("type") for claim in claims.values()
                if claim.get("status") == "verified"
                and claim.get("subject_ref") in current_ids
            }
            missing = set(_list(target.get("required_claims"))) - verified_types
            if missing:
                error("E_COMPLETION_GAP", "$.run.claims", f"目标 {object_ref} 缺少已验证 Claim", sorted(missing))


def _report(errors: list[dict[str, Any]], warnings: list[dict[str, Any]], derived: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": not errors,
        "strict_valid": not errors and not warnings,
        "errors": errors,
        "warnings": warnings,
        "derived": derived,
        "counts": {"errors": len(errors), "warnings": len(warnings)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="workflow contract JSON")
    parser.add_argument("--report-json", type=Path, help="write a JSON report")
    parser.add_argument("--strict", action="store_true", help="treat warnings as blocking")
    parser.add_argument("--quiet", action="store_true", help="suppress console report")
    args = parser.parse_args(argv)

    try:
        raw = args.contract.read_bytes()
        document = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report = validate_document(document)
    report["artifact"] = {
        "path": str(args.contract.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }

    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if (report["strict_valid"] if args.strict else report["valid"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
