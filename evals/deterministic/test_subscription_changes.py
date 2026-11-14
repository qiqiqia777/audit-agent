import pytest

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore


def test_versioned_clarification_and_ambiguous_reply(tmp_path):
    store = ProcurementStore(tmp_path / "applications.sqlite")
    staff = {"applicant@example.test": "设计", "other@example.test": "研发"}

    def mail(key, subject, body, sender="applicant@example.test", reply=""):
        return store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                subject,
                {
                    "from": sender,
                    "subject": subject,
                    "email_thread": body,
                    "message_id": f"<{key}>",
                    "in_reply_to": reply,
                },
            ),
            staff,
        )

    initial = "采购对象：软件\n业务用途：制图\n席位数：5\n订阅期限：12个月\n报价：120元/月"
    first = mail("first", "软件订阅申请 A", initial)
    second = mail("second", "软件订阅申请 B", initial)
    assert store.detail(first, "设计")["review"]["estimated_total_cny"] is None
    assert mail("reply", "Re: 软件订阅申请 A", "每席位每月 120 元", reply="<first>") == first
    assert store.detail(first, "设计")["review"]["estimated_total_cny"] == "7200.00"
    assert mail("ambiguous", "补充", "改成 8 席") is None
    assert store.detail(first, "设计")["materials"]["seats"] == 5
    assert store.detail(second, "设计")["materials"]["seats"] == 5
    assert not store.pending_changes("研发")
    (change,) = store.pending_changes("设计")
    assert change["candidates"] == [first, second]
    store.assign_change(change["mail_key"], first, "设计")
    result = store.detail(first, "设计")
    assert result["changes"]["预计总额"] == ("7200.00", "11520.00")
    assert result["changes"]["seats"] == (5, 8)
    assert mail("ambiguous", "补充", "改成 8 席") == first
    assert store.detail(first, "设计")["version"] == 3
    with pytest.raises(ValueError):
        store.decide(first, "设计", "design", 2, "approved")
    store.decide(first, "设计", "design", 3, "approved")
    assert store.detail(second, "设计")["cases"][0]["id"] == first
    other = mail("other", "软件订阅申请", initial, sender="other@example.test")
    assert not store.detail(other, "研发")["cases"]
    assert (
        mail("forged", f"申请 #{second}", "全部席位合计每月120元", sender="other@example.test")
        is None
    )
