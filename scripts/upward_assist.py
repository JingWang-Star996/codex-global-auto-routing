#!/usr/bin/env python3
"""Fail-closed R10 upward-assist request validator and one-shot reservation gate."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

MAX_REQUEST_BYTES = 32 * 1024
ROOT_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
WORK_UNIT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
REQUEST_KEYS = {"schema_version", "root_thread_id", "requester_thread_id", "work_unit_id", "coordinator_model", "authorization", "trigger", "evidence_refs", "blockers", "read_only", "task_packet", "max_output_chars", "max_attempts"}
AUTH_KEYS = {"approved", "scope", "root_thread_id", "message_ref"}
TRIGGERS = {"bounded_complexity", "unresolved_evidence_conflict", "independent_cross_model_review"}


class GateError(Exception):
    """Expected fail-closed rejection, intentionally without request echoing."""


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError("duplicate JSON key")
        result[key] = value
    return result


def _read_request(request_path: str | os.PathLike[str]) -> tuple[dict[str, Any], str]:
    try:
        with Path(request_path).open("rb") as handle:
            payload = handle.read(MAX_REQUEST_BYTES + 1)
    except OSError as exc:
        raise GateError("request unavailable") from exc
    if len(payload) > MAX_REQUEST_BYTES:
        raise GateError("request too large")
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, GateError) as exc:
        raise GateError("invalid request JSON") from exc
    if not isinstance(value, dict):
        raise GateError("request must be an object")
    return value, hashlib.sha256(payload).hexdigest()


def _string(value: Any, maximum: int, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()) or len(value) > maximum:
        raise GateError(f"invalid {name}")
    return value


def _integer(value: Any, exact: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != exact:
        raise GateError(f"invalid {name}")


def _normal_root(value: Any) -> str:
    if not isinstance(value, str) or not ROOT_UUID.fullmatch(value):
        raise GateError("invalid root thread id")
    try:
        parsed = str(uuid.UUID(value))
    except ValueError as exc:
        raise GateError("invalid root thread id") from exc
    if parsed != value:
        raise GateError("root thread id must be lower-case canonical UUID")
    return parsed


def _validate(value: dict[str, Any], request_sha256: str) -> dict[str, Any]:
    if set(value) != REQUEST_KEYS:
        raise GateError("unknown or missing request fields")
    _integer(value["schema_version"], 1, "schema version")
    root = _normal_root(value["root_thread_id"])
    if _normal_root(value["requester_thread_id"]) != root:
        raise GateError("requester is not root coordinator")
    work_unit = _string(value["work_unit_id"], 80, "work unit")
    if not WORK_UNIT.fullmatch(work_unit):
        raise GateError("invalid work unit")
    if value["coordinator_model"] != "gpt-5.6-sol":
        raise GateError("coordinator model is not eligible")
    auth = value["authorization"]
    if not isinstance(auth, dict) or set(auth) != AUTH_KEYS or auth.get("approved") is not True:
        raise GateError("authorization is not approved")
    if auth.get("scope") != "current_root_task" or _normal_root(auth.get("root_thread_id")) != root:
        raise GateError("authorization scope mismatch")
    auth_ref = _string(auth.get("message_ref"), 300, "authorization reference")
    if not isinstance(value["trigger"], str) or value["trigger"] not in TRIGGERS:
        raise GateError("invalid trigger")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 5:
        raise GateError("invalid evidence refs")
    for ref in refs:
        _string(ref, 500, "evidence reference")
    if not isinstance(value["blockers"], list) or value["blockers"]:
        raise GateError("blockers must be empty")
    if value["read_only"] is not True:
        raise GateError("request is not read-only")
    task_packet = _string(value["task_packet"], 8000, "task packet")
    _integer(value["max_output_chars"], 3000, "max output chars")
    _integer(value["max_attempts"], 1, "max attempts")
    return {"root_thread_id": root, "work_unit_id": work_unit, "request_sha256": request_sha256, "authorization_ref": auth_ref, "task_packet": task_packet}


def _spawn_message(check: dict[str, Any], reservation_sha256: str) -> str:
    summary = json.dumps({"status": "reserved", "reservation_created": True, "root_thread_id": check["root_thread_id"], "work_unit_id": check["work_unit_id"], "request_sha256": check["request_sha256"], "reservation_sha256": reservation_sha256}, separators=(",", ":"), sort_keys=True)
    message = ("work_unit_id: " + check["work_unit_id"] + "\nroot_thread_id: " + check["root_thread_id"] +
               "\nauthorization_ref: " + check["authorization_ref"] + "\nreservation_sha256: " + reservation_sha256 +
               "\nreservation_created=true\nreservation_summary: " + summary + "\n\n" + check["task_packet"])
    if len(message) > 8000:
        raise GateError("spawn message too large")
    return message


def _public(check: dict[str, Any], *, allowed: bool, can_spawn: bool, can_reserve: bool, reservation_path: str | None = None, reservation_sha256: str | None = None, message: str | None = None) -> dict[str, Any]:
    spawn_args = {"agent_type": "astra_specialist", "fork_turns": "none"}
    if message is not None:
        spawn_args["message"] = message
    result = {"allowed": allowed, "schema_valid": True, "can_reserve": can_reserve, "can_spawn": can_spawn, "spawn_args": spawn_args, "request_sha256": check["request_sha256"], "authorization_is_coordinator_attestation": True, "host_enforcement": False}
    if reservation_path is not None:
        result["reservation_path"] = reservation_path
        result["reservation_sha256"] = reservation_sha256
    return result


def check_request(request_path: str | os.PathLike[str]) -> dict[str, Any]:
    value, digest = _read_request(request_path)
    return _public(_validate(value, digest), allowed=False, can_spawn=False, can_reserve=True)


def reserve(request_path: str | os.PathLike[str], state_root: str | os.PathLike[str]) -> dict[str, Any]:
    value, digest = _read_request(request_path)
    check = _validate(value, digest)  # Do not create state until this succeeds.
    root = Path(state_root)
    # Build and length-check the complete ledger-dependent packet before any state write.
    record = {"schema_version": 1, "root_thread_id": check["root_thread_id"], "work_unit_id": check["work_unit_id"], "request_sha256": digest, "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"), "used_attempts": 1, "status": "reserved", "authorization_ref": check["authorization_ref"]}
    content = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    reservation_sha256 = hashlib.sha256(content).hexdigest()
    message = _spawn_message(check, reservation_sha256)
    try:
        root.mkdir(parents=True, exist_ok=True)
        path = root / (check["root_thread_id"] + ".json")
        # x is O_CREAT|O_EXCL: any extant (including malformed) ledger denies reuse.
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, TypeError, ValueError) as exc:
        raise GateError("reservation unavailable") from exc
    return _public(check, allowed=True, can_spawn=True, can_reserve=False, reservation_path=str(path), reservation_sha256=reservation_sha256, message=message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R10 upward-assist local preflight gate")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "reserve"):
        item = sub.add_parser(name)
        item.add_argument("--request", required=True)
        if name == "reserve":
            item.add_argument("--state-root", required=True)
    args = parser.parse_args(argv)
    try:
        result = check_request(args.request) if args.command == "check" else reserve(args.request, args.state_root)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except GateError:
        print(json.dumps({"allowed": False, "schema_valid": False, "can_reserve": False, "can_spawn": False, "reason": "request_denied", "authorization_is_coordinator_attestation": True, "host_enforcement": False}, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
