"""One procurement smoke task through the real store/worker; no mail transport."""

import argparse
import hashlib
import json
import subprocess
import time
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_worker import work_once
from minihermes.config import Settings
from minihermes.loop.models import get_client
from minihermes.ops.procurement_review import POLICY_PATH


REPO = Path(__file__).resolve().parents[2]
TASK_PATH = Path(__file__).with_name("software-per-seat.json")
GRADER_VERSION = "1"


def load_task():
    return json.loads(TASK_PATH.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_value),
                    encoding="utf-8")


def json_value(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return vars(value)


def scripted_client():
    """A fixed calibration trajectory, independent of the task's answer fields."""
    from evals.helpers import ScriptedClient, response, text_block, tool_block

    materials = {
        "item": "设计软件", "purpose": "出图", "seats": 5, "months": 12,
        "amount": "120", "billing_period": "monthly", "price_basis": "per_seat",
    }
    quotes = {
        "item": "设计软件", "purpose": "出图", "seats": "5个席位", "months": "12个月",
        "amount": "120元", "billing_period": "每月120元", "price_basis": "每席位每月120元",
    }
    return ScriptedClient([
        response([
            tool_block("read_request", {}, "a"), tool_block("read_policy", {}, "b"),
            tool_block("search_cases", {}, "c"),
        ], "tool_use"),
        response([tool_block("submit_review", {
            "materials": materials, "evidence": quotes, "clause_ids": ["SW-1", "SW-2"],
            "case_ids": [], "summary": "材料齐全，交负责人审批。",
        }, "d")], "tool_use"),
        response([text_block("建议已提交")]),
    ])


def money_equal(actual, expected):
    try:
        value = Decimal(str(actual))
        return value.is_finite() and value == Decimal(expected)
    except (InvalidOperation, ValueError, TypeError):
        return False


def grade(task, observed):
    """All checks are required. Evidence absent or invalid always fails closed."""
    expected = task["expected"]
    materials = observed.get("materials", {})
    review = observed.get("review", {})
    checks = []

    def check(ident, actual, target, passed, evidence):
        checks.append({"id": ident, "actual": actual, "expected": target,
                       "passed": bool(passed), "evidence_ref": evidence})

    for key, target in expected["materials"].items():
        actual = materials.get(key)
        correct = money_equal(actual, target) if key == "amount" else (
            type(actual) is type(target) and actual == target
        )
        check("materials." + key, actual, target, correct, "observed.json#/materials/" + key)
    actual = review.get("estimated_total_cny")
    target = expected["estimated_total_cny"]
    check("total", actual, target, money_equal(actual, target),
          "observed.json#/review/estimated_total_cny")
    for ident, actual, target, ref in [
        ("model_review", (observed.get("model_review") or {}).get("state"),
         expected["model_review_state"], "observed.json#/model_review"),
        ("review_status", review.get("status"), expected["review_status"], "observed.json#/review"),
        ("decision", observed.get("decision"), expected["decision"], "observed.json#/decision"),
        ("outbound_count", observed.get("outbound_count"), expected["outbound_count"],
         "observed.json#/outbound_count"),
    ]:
        present = "decision" in observed if ident == "decision" else actual is not None
        check(ident, actual, target, present and type(actual) is type(target) and actual == target,
              ref)
    evidence = review.get("evidence", {})
    supported = all(isinstance(evidence.get(key), str) and evidence[key].strip()
                    and evidence[key] in task["message"] for key in expected["materials"])
    check("source_evidence", evidence, "原文覆盖每个预期字段", supported,
          "observed.json#/review/evidence")
    return checks


def source_metadata():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def run_trial(task, directory, client, model, mode):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "task.json", task)
    calls = []

    def create(**kwargs):
        # Only record model messages/content, never client config, headers or exception bodies.
        call = deepcopy({key: kwargs[key] for key in
                         ("messages", "system", "tools", "max_tokens", "model")})
        calls.append(call)
        try:
            reply = client.messages.create(**kwargs)
            call["response"] = json.loads(json.dumps(reply.content, default=json_value))
            return reply
        except Exception as exc:
            call["error_class"] = type(exc).__name__
            raise
        finally:
            write_json(directory / "calls.json", calls)

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    observed, job = {}, {"result": None, "error": None}
    source, policy_version, harness_error = None, None, None
    try:
        source = source_metadata()
        policy_version = json.loads(POLICY_PATH.read_text(encoding="utf-8"))["version"]
        store = ProcurementStore(directory / "application.sqlite", model_review=True)
        sender = "fictional@example.test"
        ident = store.intake(Event(EventType.EMAIL_INBOUND, task["subject"], {
            "from": sender, "subject": task["subject"],
            "message_id": "<procurement-smoke@fictional.test>", "email_thread": task["message"],
        }), {sender: task["department"]})
        work_once(store, SimpleNamespace(messages=SimpleNamespace(create=create)), model)
        observed = store.detail(ident, task["department"])
        with closing(store.connect()) as db:
            job = dict(db.execute("SELECT * FROM review_jobs ORDER BY id DESC LIMIT 1").fetchone())
            # Count attempts, including failed sends, rather than only successful deliveries.
            observed["outbound_count"] = (
                db.execute("SELECT COUNT(*) FROM notification_attempts").fetchone()[0]
                + db.execute("SELECT COUNT(*) FROM followup_attempts").fetchone()[0]
            )
    except Exception as exc:
        # A failed DB/worker/read is a failed trial too. Preserve available files;
        # never serialize exception bodies, which can contain adapter secrets.
        harness_error = type(exc).__name__
    write_json(directory / "calls.json", calls)
    write_json(directory / "observed.json", observed)
    write_json(directory / "job.json", job)
    checks = grade(task, observed)
    result = {
        "task_id": task["id"], "task_version": task["task_version"], "trial_id": "1",
        "label_status": task["label_status"], "grader_version": GRADER_VERSION,
        "task_sha256": hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest(),
        "source": source, "mode": mode, "model": model,
        "policy_version": policy_version,
        "started_at": started_at,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "tokens": None, "cost": None, "calls": len(calls), "worker_error": job["error"],
        "harness_error": harness_error,
        "trace": json.loads(job["result"])["trace"] if job["result"] else [],
        "observed": observed, "checks": checks,
        "passed": not harness_error and not job["error"] and all(c["passed"] for c in checks),
        "evidence_refs": [name for name in (
            "application.sqlite", "task.json", "observed.json", "job.json", "calls.json"
        ) if (directory / name).is_file()],
    }
    write_json(directory / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new directory; never overwritten")
    parser.add_argument("--live", action="store_true", help="explicitly call configured GLM model")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    client, model, mode = None, "offline-script", "offline"
    if args.live:
        if not args.env_file:
            parser.error("--live requires --env-file with GLM settings")
        values = dotenv_values(args.env_file)
        if not all(values.get(key) for key in ("GLM_API_KEY", "GLM_BASE_URL", "GLM_MODEL")):
            parser.error("incomplete GLM configuration")
        settings = Settings(provider="openai", api_key=values["GLM_API_KEY"],
                            base_url=values["GLM_BASE_URL"], model=values["GLM_MODEL"])
        client, model, mode = get_client(settings), settings.model, "live"
    args.output.mkdir(parents=True, exist_ok=False)
    result = run_trial(load_task(), args.output / "trial-1", client or scripted_client(), model, mode)
    # Evidence paths within each result are relative to its trial directory.
    result["evidence_directory"] = "trial-1"
    (args.output / "results.jsonl").write_text(
        json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = ["# 采购评测冒烟报告", "", f"模式：{mode}；模型：{model}",
             f"任务：{result['task_id']} v{result['task_version']}；Grader：{GRADER_VERSION}",
             f"通过：{int(result['passed'])}/1；耗时：{result['elapsed_seconds']} 秒", "",
             "仅一个任务一次Trial，不代表统计准确率或公开Benchmark成绩。",
             "Task为工程预期，尚待用户人工核对；Token/费用未采集。", "",
             "证据：trial-1/；机器结果：results.jsonl。每项引用相对于trial-1。", "",
             "| 检查 | 通过 | 实际 | 预期 | 证据 |", "|---|---|---|---|---|"]
    for check in result["checks"]:
        cells = [check["id"], str(check["passed"]), str(check["actual"]),
                 str(check["expected"]), check["evidence_ref"]]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    (args.output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{mode}: {int(result['passed'])}/1; {args.output / 'summary.md'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
