import pytest

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore


def test_followup_success_starts_timer_and_reply_cancels_reminder(tmp_path):
    path = tmp_path / "requests.sqlite"
    store = ProcurementStore(path)
    sender = "employee@example.test"
    staff = {sender: "设计"}

    def mail(key, subject, body):
        return Event(
            EventType.EMAIL_INBOUND,
            subject,
            {"from": sender, "subject": subject, "message_id": key, "email_thread": body},
        )

    ident = store.intake(mail("<a>", "软件订阅申请", "采购对象：软件\n报价：120元/月"), staff)
    (draft,) = store.followups(ident, "设计", 100)
    assert draft["state"] == "draft" and draft["due_at"] is None
    assert len(store.followups(ident, "设计", 10000)) == 1
    store.claim_followup(ident, "设计", draft["id"])
    store.finish_followup(draft["id"], "sent", 10005, 60, "<request>")
    store = ProcurementStore(path)
    assert len(store.followups(ident, "设计", 10064)) == 1
    sent, reminder = store.followups(ident, "设计", 10065)
    assert sent["due_at"] == 10065 and reminder["kind"] == "reminder"
    assert len(store.followups(ident, "设计", 10070)) == 2
    reply = mail("<b>", f"Re: 采购申请 #{ident} 补件", "每席位每月120元")
    assert store.intake(reply, staff) == ident
    assert store.intake(reply, staff) == ident
    with pytest.raises(ValueError):
        store.claim_followup(ident, "设计", reminder["id"])
    assert store.followups(ident, "设计", 10080)[1]["state"] == "cancelled"


def test_reply_to_outbound_message_without_application_number(tmp_path):
    store = ProcurementStore(tmp_path / "threading.sqlite")
    staff = {"employee@example.test": "设计"}

    def mail(mid, body, subject="软件订阅申请", reply=""):
        return Event(
            EventType.EMAIL_INBOUND,
            subject,
            {
                "from": "employee@example.test",
                "subject": subject,
                "message_id": mid,
                "email_thread": body,
                "in_reply_to": reply,
            },
        )

    ident = store.intake(mail("<initial>", "采购对象：软件\n报价：120元/月"), staff)
    (draft,) = store.followups(ident, "设计", 100)
    claimed = store.claim_followup(ident, "设计", draft["id"])
    mid = claimed["message_id"]
    store.finish_followup(draft["id"], "sent", 100, 60, mid)
    assert store.intake(mail(mid, draft["body"], "采购申请 #1 补件"), staff) is None
    assert store.intake(mail("<answer>", "全部席位合计每月120元", "Re: 补充", mid), staff) == ident
    assert store.detail(ident, "设计")["materials"]["price_basis"] == "all_seats"


def test_rewritten_outbound_id_can_anchor_employee_reply(tmp_path):
    store = ProcurementStore(tmp_path / "provider.sqlite")
    staff = {"employee@example.test": "设计"}

    def event(mid, body, **extra):
        return Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": "employee@example.test",
                "subject": "软件订阅申请" if not extra else "Re: 补件",
                "message_id": mid,
                "email_thread": body,
                **extra,
            },
        )

    ident = store.intake(event("<initial>", "采购对象：软件\n报价：120元/月"), staff)
    (draft,) = store.followups(ident, "设计", 1)
    claimed = store.claim_followup(ident, "设计", draft["id"])
    store.finish_followup(draft["id"], "sent", 1, 60, claimed["message_id"])
    copy = event("<provider-rewritten>", "需要补件", audit_message_id=claimed["message_id"])
    copy.metadata["from"] = "procurement@example.test"
    assert store.intake(copy, staff) is None
    reply = event("<employee-answer>", "每席位每月120元", in_reply_to="<provider-rewritten>")
    assert store.intake(reply, staff) == ident
    assert store.detail(ident, "设计")["materials"]["price_basis"] == "per_seat"
