import pytest

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore


def test_equipment_event_survives_restart_and_is_scoped_to_department(tmp_path):
    path = tmp_path / "applications.sqlite"
    staff = {"employee@example.test": "设计部"}
    event = Event(
        EventType.EMAIL_INBOUND,
        "设备采购申请",
        {
            "subject": "设备采购申请：显示器",
            "message_id": "<1@example.test>",
            "from": "Employee <employee@example.test>",
            "email_thread": "采购对象：显示器\n业务用途：校色\n规格：27英寸\n数量：2\n报价：1200.55元\n费用口径：单价",
        },
    )
    app_id = ProcurementStore(path).intake(event, staff)
    reopened = ProcurementStore(path)
    assert reopened.intake(event, staff) == app_id
    report = reopened.detail(app_id, "设计部")["review"]
    assert report["estimated_total_cny"] == "2401.10"
    assert report["status"] == "ready_for_review"
    with pytest.raises(LookupError):
        reopened.detail(app_id, "销售部")
    assert reopened.intake(event, {}) is None


def test_mailbox_persists_before_cursor_and_decision_is_once_only(tmp_path):
    from datetime import datetime
    from email_agent.procurement_mailbox import ProcurementInbox
    from email_agent.sources.imap_poller import ImapPoller
    from test_imap_poller import FakeClient, FakeMessage, IMAP

    msg = FakeMessage(
        "11",
        "设备采购申请",
        datetime.now(),
        "<equipment@example.test>",
        "采购对象：键盘\n规格：USB\n业务用途：办公\n数量：1\n报价：90\n费用口径：总价",
    )
    path = tmp_path / "app.sqlite"
    store = ProcurementStore(path)
    inbox = ProcurementInbox(store, {msg.from_: "设计部"})

    def poll():
        return ImapPoller(
            inbox, IMAP, tmp_path, client_factory=lambda: FakeClient([msg])
        ).poll_once()

    assert poll() == 1
    assert poll() == 0
    store = ProcurementStore(path)
    (app,) = store.inbox("设计部")
    assert not store.inbox("销售部")
    with pytest.raises(LookupError):
        store.decide(app["id"], "销售部", "sales", 1, "approved")
    with pytest.raises(ValueError):
        store.decide(app["id"], "设计部", "design", 0, "approved")
    record = store.decide(app["id"], "设计部", "design", 1, "approved")
    assert record["decision"] == "approved" and record["notification_status"] == "pending"
    assert record["decided_at"] and record["decided_by"] == "design"
    with pytest.raises(ValueError):
        store.decide(app["id"], "设计部", "design", 1, "rejected")
