"""Compare a frozen route request with one child's actual transcript metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib


def validate(profile_path, transcript_path, *, child_id, parent_id, requested_model,
             requested_effort, registered_model, turn_id=None):
    profile_path, transcript_path = Path(profile_path), Path(transcript_path)
    profile = tomllib.loads(profile_path.read_text(encoding="utf-8-sig"))
    metas, contexts = [], []
    with transcript_path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            item = json.loads(line)
            payload = item.get("payload", {})
            if item.get("type") == "session_meta":
                metas.append(payload)
            elif item.get("type") == "turn_context":
                contexts.append(payload)
    errors = []
    meta = metas[0] if len(metas) == 1 else {}
    if len(metas) != 1:
        errors.append("exactly one session_meta required")
    if meta.get("id") != child_id or meta.get("parent_thread_id") != parent_id:
        errors.append("child or parent identity mismatch")
    role = meta.get("agent_role")
    if role is None:
        source = meta.get("source")
        if isinstance(source, dict):
            role = source.get("subagent", {}).get("thread_spawn", {}).get("agent_role")
    if role != profile.get("name"):
        errors.append("actual role does not match profile")
    if turn_id:
        selected = [item for item in contexts if item.get("turn_id") == turn_id]
    else:
        selected = contexts
    unique = {json.dumps(item, sort_keys=True) for item in selected}
    context = selected[-1] if len(unique) == 1 else {}
    if not context:
        errors.append("missing or ambiguous turn_context; specify exact turn_id")
    actual_model = context.get("model")
    actual_effort = context.get("effort", context.get("reasoning_effort"))
    if requested_model != registered_model:
        errors.append("registered model does not match request")
    if actual_model != requested_model:
        errors.append("actual model does not match request")
    if actual_effort != requested_effort:
        errors.append("actual effort does not match request")
    sandbox = context.get("sandbox_policy")
    actual_sandbox = sandbox.get("type") if isinstance(sandbox, dict) else None
    return {
        "route_model_verified": not errors,
        "errors": errors,
        "child_id": child_id,
        "parent_id": parent_id,
        "actual_role": role,
        "turn_id": context.get("turn_id"),
        "requested_model": requested_model,
        "requested_effort": requested_effort,
        "registered_model": registered_model,
        "configured_model": profile.get("model"),
        "configured_effort": profile.get("model_reasoning_effort"),
        "configured_sandbox": profile.get("sandbox_mode"),
        "actual_model": actual_model,
        "actual_effort": actual_effort,
        "actual_sandbox": actual_sandbox,
        "sandbox_matches_profile": actual_sandbox == profile.get("sandbox_mode"),
        "host_enforcement_proven": False,
        "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "transcript_sha256": hashlib.sha256(transcript_path.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("profile", "transcript", "child-id", "parent-id", "requested-model",
                "requested-effort", "registered-model"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--turn-id")
    parser.add_argument("--report-json")
    args = parser.parse_args()
    try:
        report = validate(args.profile, args.transcript, child_id=args.child_id,
                          parent_id=args.parent_id, requested_model=args.requested_model,
                          requested_effort=args.requested_effort,
                          registered_model=args.registered_model, turn_id=args.turn_id)
    except (OSError, ValueError, TypeError) as error:
        report = {"route_model_verified": False, "errors": [str(error)],
                  "host_enforcement_proven": False}
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report_json:
        destination = Path(args.report_json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if report["route_model_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
