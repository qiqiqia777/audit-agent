import re
import time

import pytest

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_web import create_app


def listing(tmp_path):
    store = ProcurementStore(tmp_path / "list.sqlite")
    staff = {"design@example.test": "设计", "sales@example.test": "销售"}

    def add(marker, body, sender="design@example.test", subject="软件订阅申请"):
        return store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                "",
                {
                    "from": sender,
                    "message_id": f"<{marker}@test>",
                    "subject": subject,
                    "email_thread": body,
                },
            ),
            staff,
        )

    full = "采购对象：协作设计软件\n业务用途：设计出图\n席位数：5\n订阅期限：12个月\n报价：120元/月\n费用口径：每席"
    ready = add("ready", full)
    approved = add(
        "approved",
        "采购对象：显示器\n业务用途：校色\n规格：27英寸\n数量：1\n报价：100\n费用口径：总价",
        subject="设备采购申请",
    )
    store.decide(approved, "设计", "lead", 1, "approved")
    attempt = store.detail(approved, "设计")["notification_attempts"][-1]
    store.claim_notification(approved, "设计", "lead", attempt["id"])
    missing = full.replace("\n费用口径：每席", "")
    waiting = add("waiting", missing)
    draft = store.followups(waiting, "设计", time.time())[0]
    store.claim_followup(waiting, "设计", draft["id"])
    store.finish_followup(draft["id"], "sent", time.time(), 3600)
    confirm = add("confirm", missing)
    store.followups(confirm, "设计", time.time())
    foreign = add(
        "foreign", full.replace("协作设计软件", "销售部保密采购"), sender="sales@example.test"
    )
    client = create_app(store, {"lead": {"department": "设计"}}, lambda r, body: None).test_client()
    with client.session_transaction() as session:
        session.update(manager="lead", csrf="list-test")
    return (
        store,
        client,
        {
            "ready": ready,
            "approved": approved,
            "waiting": waiting,
            "confirm": confirm,
            "foreign": foreign,
        },
        add,
        full,
    )


def ids(response):
    return {int(x) for x in re.findall(r'data-request-id="(\d+)"', response.get_data(as_text=True))}


def test_list_separates_approval_delivery_and_department(tmp_path):
    store, client, rows, _, _ = listing(tmp_path)
    before = store.detail(rows["approved"], "设计")
    response = client.get("/")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert ids(response) == {rows[k] for k in ["ready", "approved", "waiting", "confirm"]}
    assert "7200.00" in page and "协作设计软件" in page
    assert "已批准" in page and "结果邮件待核实" in page
    assert "销售部保密采购" not in page
    assert store.detail(rows["approved"], "设计") == before


def test_exception_view_reuses_filters_and_links_to_actual_send_history(tmp_path):
    _, client, rows, _, _ = listing(tmp_path)
    response = client.get("/?view=exceptions&decision=approved&mail=unknown")
    assert ids(response) == {rows["approved"]}
    assert f"/requests/{rows['approved']}#sending-records" in response.get_data(as_text=True)
    assert ids(client.get("/?view=exceptions&q=找不到的采购")) == set()
    assert "没有符合条件的申请" in client.get("/?view=exceptions&q=找不到的采购").get_data(
        as_text=True
    )


@pytest.mark.parametrize(
    "task,key",
    [
        ("approve", "ready"),
        ("confirm_followup", "confirm"),
        ("waiting_requester", "waiting"),
        ("verify_delivery", "approved"),
    ],
)
def test_next_actor_filters_do_not_treat_waiting_as_manager_action(tmp_path, task, key):
    _, client, rows, _, _ = listing(tmp_path)
    assert ids(client.get("/?task=" + task)) == {rows[key]}


def test_search_is_literal_escaped_and_pagination_stays_scoped(tmp_path):
    _, client, rows, add, full = listing(tmp_path)
    for n in range(22):
        add(f"extra{n}", full.replace("协作设计软件", f"工具{n}"))
    first, second = client.get("/"), client.get("/?page=2")
    assert len(ids(first)) == 20 and len(ids(second)) == 6
    assert ids(first).isdisjoint(ids(second)) and rows["foreign"] not in ids(first) | ids(second)
    q = client.get("/?q=%3Cscript%3Ealert(1)%3C/script%3E").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in q and "&lt;script&gt;" in q
    assert ids(client.get("/?q=%25")) == set()


@pytest.mark.parametrize(
    "query", ["page=0", "page=bad", "category=secret", "mail=anything", "task=arbitrary"]
)
def test_invalid_filter_returns_bad_request(tmp_path, query):
    _, client, _, _, _ = listing(tmp_path)
    assert client.get("/?" + query).status_code == 400


def test_missing_materials_are_manager_work_before_draft_is_materialized(tmp_path):
    store, client, rows, add, full = listing(tmp_path)
    missing = add("not-opened", full.replace("\n费用口径：每席", ""))
    with store.connect() as db:
        assert (
            db.execute(
                "select count(*) from followups where application_id=?", (missing,)
            ).fetchone()[0]
            == 0
        )
    assert missing in ids(client.get("/?task=confirm_followup"))
    with store.connect() as db:
        assert (
            db.execute(
                "select count(*) from followups where application_id=?", (missing,)
            ).fetchone()[0]
            == 0
        )


def test_closed_old_followup_is_not_a_current_delivery_exception(tmp_path):
    store, client, rows, add, _ = listing(tmp_path)
    draft = store.followups(rows["confirm"], "设计", time.time())[0]
    store.claim_followup(rows["confirm"], "设计", draft["id"])
    store.finish_followup(draft["id"], "unknown", time.time(), 3600)
    assert ids(client.get("/?view=exceptions&task=verify_delivery")) == {
        rows["approved"],
        rows["confirm"],
    }
    add("clear-reply", "每席位每月120元", subject=f"采购申请 #{rows['confirm']}")
    assert rows["confirm"] not in ids(client.get("/?view=exceptions"))
    assert rows["confirm"] in ids(client.get("/?task=approve"))


def test_due_reminder_changes_next_actor_without_counting_as_waiting(tmp_path):
    store, client, rows, _, _ = listing(tmp_path)
    store.followups(rows["waiting"], "设计", time.time() + 3601)
    assert rows["waiting"] in ids(client.get("/?task=confirm_followup"))
    assert rows["waiting"] not in ids(client.get("/?task=waiting_requester"))


def test_legacy_decision_without_summary_uses_migrated_attempt_read_only(tmp_path):
    store, client, rows, _, _ = listing(tmp_path)
    ident = rows["approved"]
    with store.connect() as db:
        db.execute("delete from notification_attempts where application_id=?", (ident,))
        db.execute("update applications set notification_status=NULL where id=?", (ident,))
        db.commit()
    ProcurementStore(store.path)
    before = store.detail(ident, "设计")
    assert before["notification_status"] is None
    assert before["notification_attempts"][-1]["state"] == "unknown"
    response = client.get("/?view=exceptions&task=verify_delivery&mail=unknown")
    assert ids(response) == {ident}
    assert "结果邮件待核实" in response.get_data(as_text=True)
    assert f"/requests/{ident}#sending-records" in response.get_data(as_text=True)
    assert store.detail(ident, "设计") == before
