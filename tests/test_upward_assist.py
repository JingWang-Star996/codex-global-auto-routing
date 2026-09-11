import concurrent.futures
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import uuid
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
QA = ROOT / "tests" / ".release-test-output" / ("gate-" + uuid.uuid4().hex)
QA.mkdir(parents=True, exist_ok=False)
SPEC = importlib.util.spec_from_file_location("upward_assist", ROOT / "scripts" / "upward_assist.py")
UP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UP)

def request(**changes):
    root = "12345678-1234-4234-9234-123456789abc"
    value = {"schema_version":1,"root_thread_id":root,"requester_thread_id":root,"work_unit_id":"gate.review-1","coordinator_model":"gpt-5.6-sol","authorization":{"approved":True,"scope":"current_root_task","root_thread_id":root,"message_ref":"user-message-1"},"trigger":"bounded_complexity","evidence_refs":["local evidence"],"blockers":[],"read_only":True,"task_packet":"Read-only independent review.","max_output_chars":3000,"max_attempts":1}
    value.update(changes)
    return value

class GateTests(unittest.TestCase):
    def write(self, value, name="request.json"):
        path=QA/(uuid.uuid4().hex+"-"+name); path.write_text(json.dumps(value),encoding="utf-8"); return path
    def test_check_has_no_state_write_and_spawn_is_frozen(self):
        path=self.write(request()); before=sorted(str(p.relative_to(QA)) for p in QA.rglob("*")); result=UP.check_request(path); after=sorted(str(p.relative_to(QA)) for p in QA.rglob("*"))
        self.assertFalse(result["allowed"]); self.assertTrue(result["schema_valid"]); self.assertTrue(result["can_reserve"]); self.assertFalse(result["can_spawn"]); self.assertEqual(before,after); self.assertEqual(result["spawn_args"],{"agent_type":"astra_specialist","fork_turns":"none"}); self.assertNotIn("message",result["spawn_args"])
    def test_reserve_once_and_concurrency(self):
        path=self.write(request()); state=QA/("state-"+uuid.uuid4().hex)
        def run():
            try:return UP.reserve(path,state)["can_spawn"]
            except UP.GateError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(results.count(True),1); self.assertEqual(results.count(False),1); self.assertFalse(run())
    def test_rejections(self):
        cases=[request(authorization={"approved":False,"scope":"current_root_task","root_thread_id":"12345678-1234-4234-9234-123456789abc","message_ref":"x"}),request(authorization={"approved":True,"scope":"current_root_task","root_thread_id":"12345678-1234-4234-9234-123456789abc","message_ref":"  "}),request(root_thread_id="BAD",requester_thread_id="BAD"),request(requester_thread_id="12345678-1234-4234-9234-123456789abd"),request(authorization={"approved":True,"scope":"current_root_task","root_thread_id":"12345678-1234-4234-9234-123456789abd","message_ref":"x"}),request(coordinator_model="gpt-6-astra"),request(coordinator_model="unknown"),request(evidence_refs=[]),request(evidence_refs=["   "]),request(blockers=["login"]),request(blockers="bad"),request(task_packet="x"*8001),request(task_packet="   "),request(read_only=False),request(schema_version=True),request(max_output_chars=True),request(max_attempts=True),request(trigger=[])]
        for value in cases:
            with self.assertRaises(UP.GateError): UP.check_request(self.write(value))
    def test_duplicate_unknown_and_bad_ledger(self):
        duplicate=QA/(uuid.uuid4().hex+"-dup.json"); duplicate.write_text('{"schema_version":1,"schema_version":1}',encoding="utf-8")
        with self.assertRaises(UP.GateError): UP.check_request(duplicate)
        nested=QA/(uuid.uuid4().hex+"-nested.json"); nested.write_text('{"schema_version":1,"root_thread_id":"12345678-1234-4234-9234-123456789abc","requester_thread_id":"12345678-1234-4234-9234-123456789abc","work_unit_id":"x","coordinator_model":"gpt-5.6-sol","authorization":{"approved":true,"approved":true},"trigger":"bounded_complexity","evidence_refs":["x"],"blockers":[],"read_only":true,"task_packet":"x","max_output_chars":3000,"max_attempts":1}',encoding="utf-8")
        with self.assertRaises(UP.GateError): UP.check_request(nested)
        with self.assertRaises(UP.GateError): UP.check_request(self.write(request(extra="no")))
        path=self.write(request()); state=QA/("bad-"+uuid.uuid4().hex); state.mkdir(); ledger=state/(request()["root_thread_id"]+".json"); ledger.write_text("not JSON",encoding="utf-8")
        with self.assertRaises(UP.GateError): UP.reserve(path,state)
    def test_oversized_and_fsync_residue_fail_closed(self):
        oversized=QA/(uuid.uuid4().hex+"-large.json"); oversized.write_bytes(b"{"+b"x"*(UP.MAX_REQUEST_BYTES+1))
        with self.assertRaises(UP.GateError): UP.check_request(oversized)
        path=self.write(request()); state=QA/("fsync-"+uuid.uuid4().hex)
        with mock.patch.object(UP.os,"fsync",side_effect=OSError("failure")):
            with self.assertRaises(UP.GateError): UP.reserve(path,state)
        self.assertTrue((state/(request()["root_thread_id"]+".json")).exists())
        with self.assertRaises(UP.GateError): UP.reserve(path,state)
    def test_subprocess_replay_and_cross_work_unit(self):
        path=self.write(request()); state=QA/("subprocess-"+uuid.uuid4().hex); command=[sys.executable,str(ROOT/"scripts"/"upward_assist.py"),"reserve","--request",str(path),"--state-root",str(state)]
        first=subprocess.run(command,capture_output=True,text=True); second=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(first.returncode,0); self.assertEqual(second.returncode,2); self.assertIn('request_denied',second.stderr)
        with self.assertRaises(UP.GateError): UP.reserve(self.write(request(work_unit_id="other-unit")),state)
    def test_root_normalization_and_receipt_hashes(self):
        value=request(); path=self.write(value); result=UP.reserve(path,QA/("receipt-"+uuid.uuid4().hex)); self.assertTrue(result["allowed"]); self.assertFalse(result["can_reserve"]); self.assertEqual(result["request_sha256"],hashlib.sha256(path.read_bytes()).hexdigest()); self.assertTrue(pathlib.Path(result["reservation_path"]).exists()); self.assertEqual(result["reservation_sha256"],hashlib.sha256(pathlib.Path(result["reservation_path"]).read_bytes()).hexdigest())
        message=result["spawn_args"]["message"]; self.assertLessEqual(len(message),8000); self.assertIn("work_unit_id: gate.review-1",message); self.assertIn("root_thread_id: 12345678-1234-4234-9234-123456789abc",message); self.assertIn("authorization_ref: user-message-1",message); self.assertIn("reservation_sha256: "+result["reservation_sha256"],message); self.assertIn("Read-only independent review.",message)
        summary=json.loads(re.search(r"^reservation_summary: (.+)$",message,re.MULTILINE).group(1)); self.assertEqual(set(summary),{"status","reservation_created","root_thread_id","work_unit_id","request_sha256","reservation_sha256"}); self.assertEqual(summary,{"status":"reserved","reservation_created":True,"root_thread_id":"12345678-1234-4234-9234-123456789abc","work_unit_id":"gate.review-1","request_sha256":result["request_sha256"],"reservation_sha256":result["reservation_sha256"]})
        value=request(root_thread_id="12345678-1234-4234-9234-123456789ABC",requester_thread_id="12345678-1234-4234-9234-123456789ABC")
        with self.assertRaises(UP.GateError): UP.check_request(self.write(value))
    def test_packet_length_unicode_and_check_drift(self):
        path=self.write(request(task_packet="中"*100)); checked=UP.check_request(path); changed=request(task_packet="changed"); path.write_text(json.dumps(changed),encoding="utf-8"); self.assertNotEqual(checked["request_sha256"],UP.check_request(path)["request_sha256"]); reserved=UP.reserve(path,QA/("changed-"+uuid.uuid4().hex)); self.assertNotEqual(checked["request_sha256"],reserved["request_sha256"])
        oversized_path=self.write(request(task_packet="x"*8000)); state=QA/("too-long-"+uuid.uuid4().hex)
        with self.assertRaises(UP.GateError): UP.reserve(oversized_path,state)
        self.assertFalse(state.exists())

if __name__ == "__main__": unittest.main()
