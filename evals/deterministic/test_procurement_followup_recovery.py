import re
import smtplib
from datetime import datetime
import time
import threading
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from werkzeug.security import generate_password_hash

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_web import create_app


def recovery_portal(tmp_path, kind, error, deliver_hook=None):
    store = ProcurementStore(tmp_path / "recovery.sqlite")
    ident = store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "message_id": "<initial@test>",
                "subject": "软件订阅申请",
                "email_thread": "采购对象：软件\n业务用途：设计\n席位数：5\n订阅期限：12个月\n报价：120元/月",
            },
        ),
        {"employee@example.test": "设计"},
    )
    draft = store.followups(ident, "设计", 100)[0]
    if kind == "reminder":
        store.claim_followup(ident, "设计", draft["id"])
        store.finish_followup(draft["id"], "sent", 100, 60)
        draft = store.followups(ident, "设计", 160)[-1]
    calls = []

    def deliver(record, body):
        calls.append((record, body))
        if deliver_hook:
            return deliver_hook(record, body)
        if len(calls) == 1:
            raise error
        return {"message_id": record["outbound_message_id"], "smtp_response": "accepted"}

    managers = {
        name: {"department": dept, "password_hash": generate_password_hash("demo")}
        for name, dept in (("manager", "设计"), ("sales", "销售"))
    }
    client = create_app(store, managers, deliver, wait_seconds=60).test_client()

    def login(name):
        token = re.search('name="csrf" value="([^"]+)"', client.get("/login").text)[1]
        assert (
            client.post(
                "/login", data={"csrf": token, "user": name, "password": "demo"}
            ).status_code
            == 302
        )
        with client.session_transaction() as session:
            return session["csrf"]

    token = login("manager")
    return store, ident, draft, client, token, calls, login


@pytest.mark.parametrize("kind", ["request", "reminder"])
@pytest.mark.parametrize("unknown", [False, True])
def test_followup_failure_can_be_verified_and_retried_once(tmp_path, kind, unknown):
    error = (
        ConnectionResetError("controlled disconnect")
        if unknown
        else smtplib.SMTPRecipientsRefused({"employee@example.test": (550, b"rejected")})
    )
    store, ident, draft, client, token, calls, _ = recovery_portal(tmp_path, kind, error)
    url = f"/requests/{ident}"
    assert client.post(url, data={"csrf": token, "followup": draft["id"]}).status_code == 302
    page = client.get(url).text
    assert ("核实补件结果" if unknown else "确认补发补件") in page
    failed = store.followups(ident, "设计", time.time())[-1]
    attempt = failed["attempts"][-1]
    assert attempt["recipient"] == "employee@example.test" and attempt["message_id"]
    retry = {"csrf": token, "followup": draft["id"], "followup_attempt": attempt["id"]}
    if unknown:
        assert client.post(url, data=retry).status_code == 409
        verify = {
            "csrf": token,
            "verify_followup": draft["id"],
            "followup_attempt": attempt["id"],
            "delivered": "no",
            "note": "",
        }
        assert client.post(url, data=verify).status_code == 409
        verify["note"] = "已核对演示收件箱，未送达"
        assert client.post(url, data=verify).status_code == 302
    assert client.post(url, data=retry).status_code == 302
    assert client.post(url, data=retry).status_code == 409
    rows = store.followups(ident, "设计", time.time())
    recovered = next(r for r in rows if r["id"] == draft["id"])
    assert recovered["state"] == "sent" and len(recovered["attempts"]) == 2
    assert calls[0][1] == calls[1][1] and len(calls) == 2
    assert store.detail(ident, "设计")["decision"] is None
    if kind == "request":
        assert recovered["due_at"] - recovered["sent_at"] == 60


def test_verified_delivery_uses_actual_send_time_and_rejects_late_result(tmp_path):
    store, ident, draft, client, token, calls, _ = recovery_portal(
        tmp_path, "request", ConnectionResetError()
    )
    url = f"/requests/{ident}"
    client.post(url, data={"csrf": token, "followup": draft["id"]})
    attempt = store.followups(ident, "设计", time.time())[0]["attempts"][-1]
    sent = datetime.fromtimestamp(time.time() - 120).replace(microsecond=0)
    verify = {
        "csrf": token,
        "verify_followup": draft["id"],
        "followup_attempt": attempt["id"],
        "delivered": "yes",
        "note": "核对服务器确认已收取",
        "sent_at": sent.isoformat(timespec="seconds"),
    }
    assert client.post(url, data=verify | {"sent_at": ""}).status_code == 409
    assert client.post(url, data=verify).status_code == 302
    store.finish_followup(draft["id"], "failed", time.time(), 60, attempt_id=attempt["id"])
    row = ProcurementStore(store.path).followups(ident, "设计", time.time())[0]
    assert row["state"] == "sent" and row["sent_at"] == sent.timestamp()
    assert row["due_at"] == sent.timestamp() + 60
    assert len(calls) == 1


def test_recovery_rejects_foreign_department_and_old_version(tmp_path):
    store, ident, draft, client, token, calls, login = recovery_portal(
        tmp_path, "request", ConnectionResetError()
    )
    url = f"/requests/{ident}"
    client.post(url, data={"csrf": token, "followup": draft["id"]})
    attempt = store.followups(ident, "设计", time.time())[0]["attempts"][-1]
    verify = {
        "verify_followup": draft["id"],
        "followup_attempt": attempt["id"],
        "delivered": "no",
        "note": "未送达",
    }
    sales_token = login("sales")
    assert client.post(url, data=verify | {"csrf": sales_token}).status_code == 404
    token = login("manager")
    assert client.post(url, data=verify | {"csrf": token}).status_code == 302
    store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "message_id": "<reply@test>",
                "subject": f"采购申请 #{ident}",
                "email_thread": "每席位每月120元",
            },
        ),
        {"employee@example.test": "设计"},
    )
    assert (
        client.post(
            url, data={"csrf": token, "followup": draft["id"], "followup_attempt": attempt["id"]}
        ).status_code
        == 409
    )
    assert len(calls) == 1


def test_retry_claim_is_atomic_and_old_completion_cannot_replace_new_attempt(tmp_path):
    store, ident, draft, _, _, _, _ = recovery_portal(tmp_path, "request", ConnectionResetError())
    first = store.claim_followup(ident, "设计", draft["id"])
    store.finish_followup(draft["id"], "unknown", 100, 60, attempt_id=first["attempt_id"])
    store.verify_followup(
        ident, "设计", draft["id"], first["attempt_id"], "manager", "no", "核实未送达", 101
    )

    def retry():
        try:
            return store.claim_followup(
                ident, "设计", draft["id"], "manager", first["attempt_id"], 60
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: retry(), range(2)))
    assert sum(r is not None for r in results) == 1
    current = next(r for r in results if r)
    with pytest.raises(ValueError, match="关联发送记录"):
        store.finish_followup(draft["id"], "sent", 102, 60)
    store.finish_followup(draft["id"], "sent", 102, 60, attempt_id=first["attempt_id"])
    row = store.followups(ident, "设计", 102)[0]
    assert row["state"] == "unknown" and row["attempts"][-1]["id"] == current["attempt_id"]
    assert row["sent_at"] is None
    copy = Event(
        EventType.EMAIL_INBOUND,
        "",
        {
            "from": "employee@example.test",
            "message_id": first["message_id"],
            "subject": "Re:补件",
            "email_thread": first["body"],
        },
    )
    assert store.intake(copy, {"employee@example.test": "设计"}) is None
    # An employee can still answer an older attempt's Message-ID after retry.
    store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "message_id": "<another@test>",
                "subject": "软件订阅申请",
                "email_thread": "采购对象：另一软件",
            },
        ),
        {"employee@example.test": "设计"},
    )
    copy.metadata.update(
        message_id="<answer-old@test>",
        in_reply_to=first["message_id"],
        email_thread="每席位每月120元",
    )
    assert store.intake(copy, {"employee@example.test": "设计"}) == ident
    assert store.detail(ident, "设计")["version"] == 2


def test_legacy_followup_history_migrates_once_without_losing_deadline(tmp_path):
    store, ident, draft, _, _, _, _ = recovery_portal(tmp_path, "request", ConnectionResetError())
    store.claim_followup(ident, "设计", draft["id"])
    store.finish_followup(draft["id"], "sent", 100, 60)
    with closing(store.connect()) as db, db:
        db.execute("DROP TABLE followup_attempts")
    for _ in range(2):
        store = ProcurementStore(store.path)
    row = store.followups(ident, "设计", 159)[0]
    assert row["due_at"] == 160 and len(row["attempts"]) == 1
    assert row["attempts"][0]["actor"] == "migration"


def test_legacy_unknown_does_not_invent_a_wait_duration(tmp_path):
    store, ident, draft, _, _, _, _ = recovery_portal(tmp_path, "request", ConnectionResetError())
    store.claim_followup(ident, "设计", draft["id"])
    store.finish_followup(draft["id"], "unknown", 100, 60)
    with closing(store.connect()) as db, db:
        db.execute("DROP TABLE followup_attempts")
    store = ProcurementStore(store.path)
    attempt = store.followups(ident, "设计", 200)[0]["attempts"][0]
    assert attempt["wait_seconds"] is None
    with pytest.raises(ValueError, match="未保存等待时长"):
        store.verify_followup(
            ident, "设计", draft["id"], attempt["id"], "manager", "yes", "已送达", 200, sent_at=100
        )
    assert store.followups(ident, "设计", 200)[0]["due_at"] is None


def test_reply_invalidates_old_verification_form(tmp_path):
    store, ident, draft, client, token, _, _ = recovery_portal(
        tmp_path, "request", ConnectionResetError()
    )
    url = f"/requests/{ident}"
    client.post(url, data={"csrf": token, "followup": draft["id"]})
    attempt = store.followups(ident, "设计", time.time())[0]["attempts"][-1]
    store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "message_id": "<answer-before-verify@test>",
                "subject": f"采购申请 #{ident}",
                "email_thread": "每席位每月120元",
            },
        ),
        {"employee@example.test": "设计"},
    )
    assert (
        client.post(
            url,
            data={
                "csrf": token,
                "verify_followup": draft["id"],
                "followup_attempt": attempt["id"],
                "delivered": "no",
                "note": "旧页面核实",
            },
        ).status_code
        == 409
    )
    assert store.followups(ident, "设计", time.time())[0]["attempts"][-1]["verified_by"] is None


@pytest.mark.parametrize("kind", ["followup", "notification"])
def test_active_delivery_cannot_be_verified_or_retried(tmp_path, kind):
    started, release = threading.Event(), threading.Event()

    def deliver(record, body):
        started.set()
        assert release.wait(5)
        return {"message_id": record["outbound_message_id"]}

    store, ident, draft, client, token, calls, _ = recovery_portal(
        tmp_path, "request", None, deliver_hook=deliver
    )
    if kind == "notification":
        store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                "",
                {
                    "from": "employee@example.test",
                    "message_id": "<complete@test>",
                    "subject": f"采购申请 #{ident}",
                    "email_thread": "每席位每月120元",
                },
            ),
            {"employee@example.test": "设计"},
        )
    other = client.application.test_client()
    with client.session_transaction() as original, other.session_transaction() as copied:
        copied.update(original)
    url = f"/requests/{ident}"
    payload = (
        {"csrf": token, "followup": draft["id"]}
        if kind == "followup"
        else {"csrf": token, "version": 2, "decision": "approved"}
    )
    with ThreadPoolExecutor(max_workers=1) as workers:
        sent = workers.submit(client.post, url, data=payload)
        try:
            assert started.wait(5)
            if kind == "followup":
                attempt = store.followups(ident, "设计", time.time())[0]["attempts"][-1]
                verify = {
                    "verify_followup": draft["id"],
                    "followup_attempt": attempt["id"],
                    "delivered": "no",
                }
                retry = {"followup": draft["id"], "followup_attempt": attempt["id"]}
            else:
                attempt = store.detail(ident, "设计")["notification_attempts"][-1]
                verify = {"verify": "no", "attempt": attempt["id"]}
                retry = {"retry": "", "attempt": attempt["id"]}
            assert (
                other.post(url, data=verify | {"csrf": token, "note": "并发核实"}).status_code
                == 409
            )
            assert other.post(url, data=retry | {"csrf": token}).status_code == 409
        finally:
            release.set()
        assert sent.result().status_code == 302
    assert len(calls) == 1


def test_process_exit_releases_delivery_lock_for_uncertain_send_recovery(tmp_path):
    store, ident, draft, _, _, _, _ = recovery_portal(tmp_path, "request", None)
    claimed = store.claim_followup(ident, "设计", draft["id"])
    code = """
import sys, time
from pathlib import Path
from email_agent.procurement import ProcurementStore
store = ProcurementStore(Path(sys.argv[1]))
with store.delivery_lock('followup', int(sys.argv[2])):
    print('locked', flush=True)
    time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-c", code, str(store.path), str(draft["id"])],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf8",
    )
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(ValueError, match="发送仍在进行"):
            store.verify_followup(
                ident, "设计", draft["id"], claimed["attempt_id"], "manager", "no", "仍在发送", 101
            )
    finally:
        child.terminate()
        child.wait(timeout=5)
        child.stdout.close()
    # No finish callback ran; a new process can still verify the interrupted attempt.
    reopened = ProcurementStore(store.path)
    reopened.verify_followup(
        ident,
        "设计",
        draft["id"],
        claimed["attempt_id"],
        "manager",
        "no",
        "原发送进程已停止，核对未送达",
        102,
    )
    assert reopened.followups(ident, "设计", 102)[0]["state"] == "failed"
