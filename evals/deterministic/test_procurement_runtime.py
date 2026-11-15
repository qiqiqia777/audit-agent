from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import threading
from types import SimpleNamespace

import pytest

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_mailbox import main


def waiting_request(tmp_path):
    store = ProcurementStore(tmp_path / "runtime.sqlite")
    staff = {"employee@example.test": "设计"}

    def inbound(mid, body, subject="软件订阅申请"):
        return store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                subject,
                {
                    "from": "employee@example.test",
                    "subject": subject,
                    "message_id": mid,
                    "email_thread": body,
                },
            ),
            staff,
        )

    ident = inbound("<initial>", "采购对象：软件\n报价：120元/月")
    (request,) = store.followups(ident, "设计", 100)
    store.claim_followup(ident, "设计", request["id"])
    store.finish_followup(request["id"], "sent", 100, 60)
    return store, ident, inbound


def test_runtime_ticks_create_only_one_due_reminder_while_other_request_finishes(tmp_path):
    store, ident, inbound = waiting_request(tmp_path)
    other = inbound(
        "<equipment>",
        "采购对象：显示器\n业务用途：设计\n规格：27英寸\n数量：1\n报价：100\n费用口径：总价",
        "设备采购申请",
    )
    store.decide(other, "设计", "manager", 1, "approved")
    store = ProcurementStore(store.path)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(store.materialize_due_followups, [160, 160]))
    with closing(store.connect()) as db:
        rows = db.execute(
            "SELECT kind,state FROM followups WHERE application_id=? ORDER BY id", (ident,)
        ).fetchall()
    assert [(r["kind"], r["state"]) for r in rows] == [("request", "sent"), ("reminder", "draft")]
    assert store.detail(other, "设计")["decision"] == "approved"


def test_reply_committed_before_send_claim_prevents_sending(tmp_path):
    store, ident, inbound = waiting_request(tmp_path)
    store.materialize_due_followups(160)
    reminder = store.followups(ident, "设计", 160)[-1]
    replied = threading.Event()

    def reply():
        inbound("<answer>", "暂时还是这份材料", f"采购申请 #{ident}")
        replied.set()

    def send_claim():
        assert replied.wait(5)
        with pytest.raises(ValueError):
            store.claim_followup(ident, "设计", reminder["id"])

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(reply)
        second = workers.submit(send_claim)
        first.result()
        second.result()
    store = ProcurementStore(store.path)
    store.materialize_due_followups(2000)
    rows = store.followups(ident, "设计", 2000)
    assert rows[0]["closed_at"] and rows[0]["due_at"] == 160
    assert rows[1]["state"] == "cancelled"
    assert rows[-1]["kind"] == "request" and rows[-1]["state"] == "draft"
    assert store.detail(ident, "设计")["version"] == 2


def test_send_claim_first_records_the_inflight_send_without_reopening_wait(tmp_path):
    store, ident, inbound = waiting_request(tmp_path)
    store.materialize_due_followups(160)
    reminder = store.followups(ident, "设计", 160)[-1]
    claimed = store.claim_followup(ident, "设计", reminder["id"])
    inbound("<answer>", "每席位每月120元", f"采购申请 #{ident}")
    store.finish_followup(claimed["id"], "sent", 161, 60, claimed["message_id"])
    store.materialize_due_followups(2000)
    rows = store.followups(ident, "设计", 2000)
    assert rows[1]["state"] == "sent" and rows[1]["closed_at"]
    assert sum(r["kind"] == "reminder" for r in rows) == 1


def test_mailbox_entrypoint_runs_due_checks_without_opening_any_page(tmp_path, monkeypatch):
    import email_agent.procurement_mailbox as mailbox

    directory = tmp_path / "procurement"
    directory.mkdir()
    store, ident, _ = waiting_request(directory)
    store.path.rename(directory / "applications.sqlite")
    # Simulate an already reviewed version in a pre-existing application DB.
    store = ProcurementStore(directory / "applications.sqlite", model_review=True)
    with closing(store.connect()) as db, db:
        db.execute(
            "INSERT INTO review_jobs(application_id,version,state) VALUES(?,1,'completed')",
            (ident,),
        )
    roster = tmp_path / "roster.json"
    roster.write_text('{"staff":{}}', encoding="utf8")
    cfg = SimpleNamespace(data_dir=tmp_path, imap=object(), poll_interval_seconds=60)
    monkeypatch.setattr(mailbox.AppConfig, "from_env", lambda _: cfg)

    class Poller:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            deadline = threading.Event()
            for _ in range(100):
                with closing(store.connect()) as db:
                    if db.execute("SELECT 1 FROM followups WHERE kind='reminder'").fetchone():
                        return
                deadline.wait(0.01)
            pytest.fail("runtime did not create overdue reminder")

    monkeypatch.setattr(mailbox, "ImapPoller", Poller)
    assert main(["--roster", str(roster)]) is None
    assert store.followups(ident, "设计", 2000)[-1]["kind"] == "reminder"


@pytest.mark.parametrize("status", ["failed", "unknown"])
def test_no_wait_timer_before_confirmed_request_send(tmp_path, status):
    store = ProcurementStore(tmp_path / "failed.sqlite")
    ident = store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "message_id": "<failed@test>",
                "subject": "软件订阅申请",
                "email_thread": "采购对象：软件",
            },
        ),
        {"employee@example.test": "设计"},
    )
    (draft,) = store.followups(ident, "设计", 100)
    store.claim_followup(ident, "设计", draft["id"])
    store.finish_followup(draft["id"], status, 100, 60)
    store = ProcurementStore(store.path)
    store.materialize_due_followups(100000)
    rows = store.followups(ident, "设计", 100000)
    assert len(rows) == 1 and rows[0]["due_at"] is None and rows[0]["sent_at"] is None


def test_legacy_followup_table_gets_close_marker_without_losing_wait(tmp_path):
    store, ident, _ = waiting_request(tmp_path)
    with closing(store.connect()) as db, db:
        db.execute("ALTER TABLE followups DROP COLUMN closed_at")
    store = ProcurementStore(store.path)
    rows = store.followups(ident, "设计", 159)
    assert len(rows) == 1 and rows[0]["due_at"] == 160 and rows[0]["closed_at"] is None
    store.materialize_due_followups(160)
    assert len(store.followups(ident, "设计", 160)) == 2


def test_two_process_roles_can_upgrade_the_same_legacy_wait_table(tmp_path):
    store, ident, _ = waiting_request(tmp_path)
    with closing(store.connect()) as db, db:
        db.execute("ALTER TABLE followups DROP COLUMN closed_at")
    with ThreadPoolExecutor(max_workers=2) as workers:
        stores = list(workers.map(lambda _: ProcurementStore(store.path), range(2)))
    assert all(s.followups(ident, "设计", 159)[0]["due_at"] == 160 for s in stores)
