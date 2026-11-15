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
