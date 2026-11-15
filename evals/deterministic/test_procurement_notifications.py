import re
import smtplib
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from werkzeug.security import generate_password_hash

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_web import create_app
from email_agent.sending.smtp import send_email


def request_store(tmp_path):
    store = ProcurementStore(tmp_path / "notifications.sqlite")
    ident = store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "message_id": "<equipment@test>",
                "subject": "设备采购申请",
                "email_thread": "采购对象：显示器\n业务用途：设计\n规格：27英寸\n数量：1\n报价：100\n费用口径：总价",
            },
        ),
        {"employee@example.test": "设计"},
    )
    return store, ident


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPRecipientsRefused({"employee@example.test": (550, b"rejected")}),
        ConnectionResetError("connection lost after DATA"),
    ],
)
def test_web_recovers_delivery_without_replacing_decision(tmp_path, error):
    store, ident = request_store(tmp_path)
    calls = []

    def deliver(row, body):
        calls.append(body)
        if len(calls) == 1:
            raise error
        return {"message_id": "<delivered@test>", "smtp_response": "DATA accepted"}

    managers = {"manager": {"department": "设计", "password_hash": generate_password_hash("demo")}}
    client = create_app(store, managers, deliver).test_client()
    login = client.get("/login").get_data(as_text=True)
    csrf = re.search('name="csrf" value="([^"]+)"', login)[1]
    client.post("/login", data={"csrf": csrf, "user": "manager", "password": "demo"})
    with client.session_transaction() as session:
        csrf = session["csrf"]
    url = f"/requests/{ident}"
    assert (
        client.post(url, data={"csrf": csrf, "version": 1, "decision": "approved"}).status_code
        == 302
    )
    original = store.detail(ident, "设计")
    attempt = original["notification_attempts"][-1]
    assert original["decision"] == "approved"
    expected = "unknown" if isinstance(error, ConnectionResetError) else "failed"
    assert attempt["state"] == expected
    store = ProcurementStore(store.path)
    retry = {"csrf": csrf, "retry": "", "attempt": attempt["id"]}
    if expected == "unknown":
        assert client.post(url, data=retry).status_code == 409
        assert len(calls) == 1
        assert (
            client.post(
                url, data={"csrf": csrf, "verify": "no", "attempt": attempt["id"], "note": ""}
            ).status_code
            == 409
        )
        assert (
            client.post(
                url,
                data={
                    "csrf": csrf,
                    "verify": "no",
                    "attempt": attempt["id"],
                    "note": "已核对收件箱和服务器记录，未送达",
                },
            ).status_code
            == 302
        )
    assert client.post(url, data=retry).status_code == 302
    assert client.post(url, data=retry).status_code == 409
    final = store.detail(ident, "设计")
    assert len(calls) == 2 and calls[0] == calls[1]
    assert (final["decision"], final["decided_by"], final["decided_at"]) == (
        original["decision"],
        original["decided_by"],
        original["decided_at"],
    )
    assert final["notification_status"] == "sent"
    assert len(final["notification_attempts"]) == 2
    assert final["notification_attempts"][-1]["message_id"] == "<delivered@test>"
    assert "已发送" in client.get(url).get_data(as_text=True)


def test_concurrent_claim_and_restart_after_decision(tmp_path):
    store, ident = request_store(tmp_path)
    app = store.decide(ident, "设计", "manager", 1, "approved")
    attempt_id = app["notification_attempts"][-1]["id"]
    store = ProcurementStore(store.path)

    def claim():
        try:
            return store.claim_notification(ident, "设计", "manager", attempt_id)["id"]
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: claim(), range(2)))
    assert results.count(attempt_id) == 1 and results.count(None) == 1
    store = ProcurementStore(store.path)
    assert store.detail(ident, "设计")["notification_status"] == "unknown"
    store.verify_notification(ident, "设计", "manager", attempt_id, "yes", "已查到员工收件")
    store.finish_notification(attempt_id, "failed", {})
    assert store.detail(ident, "设计")["notification_status"] == "sent"
    with pytest.raises(ValueError):
        store.claim_notification(ident, "设计", "manager", attempt_id)


def test_previous_decisions_migrate_idempotently(tmp_path):
    store, ident = request_store(tmp_path)
    store.decide(ident, "设计", "manager", 1, "approved")
    with closing(store.connect()) as db, db:
        db.execute("DROP TABLE notification_attempts")
        db.execute("UPDATE applications SET notification_status='unknown'")
    for _ in range(2):
        store = ProcurementStore(store.path)
    app = store.detail(ident, "设计")
    assert len(app["notification_attempts"]) == 1
    assert app["notification_attempts"][0]["state"] == "unknown"


@pytest.mark.parametrize("refused", [True, False])
def test_smtp_acceptance_uses_submission_result_not_noop(refused):
    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            if not refused:
                raise ConnectionResetError("disconnected during QUIT")

        def login(self, *args):
            pass

        def send_message(self, message):
            return {"employee@example.test": (550, b"rejected")} if refused else {}

    args = dict(
        host="smtp.test",
        port=465,
        user="sender",
        password="test",
        from_addr="sender@example.test",
        to="employee@example.test",
        subject="test",
        body="test",
        factory=SMTP,
    )
    if refused:
        with pytest.raises(smtplib.SMTPRecipientsRefused):
            send_email(**args)
    else:
        assert send_email(**args)["smtp_response"] == "DATA accepted"
