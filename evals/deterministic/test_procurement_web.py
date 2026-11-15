import re

from werkzeug.security import generate_password_hash

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_web import create_app


def test_manager_previews_then_sends_once_for_the_reviewed_version(tmp_path):
    store = ProcurementStore(tmp_path / "requests.sqlite")
    employee = "employee@example.test"
    ident = store.intake(
        Event(
            EventType.EMAIL_INBOUND,
            "",
            {
                "from": employee,
                "subject": "设备采购申请",
                "message_id": "<test@example.test>",
                "email_thread": "采购对象：显示器\n业务用途：制图\n规格：27英寸\n数量：2\n报价：100\n费用口径：单价",
            },
        ),
        {employee: "设计部"},
    )
    managers = {
        m: {"department": d, "password_hash": generate_password_hash("demo")}
        for m, d in [("design", "设计部"), ("sales", "销售部")]
    }
    outbox = []
    client = create_app(
        store, managers, lambda r, body: outbox.append((r["sender"], body))
    ).test_client()
    path = f"/requests/{ident}"

    def token(response):
        return re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))[1]

    def login(manager):
        return client.post(
            "/login",
            data={"user": manager, "password": "demo", "csrf": token(client.get("/login"))},
        )

    assert client.get(path).status_code == 302
    assert login("sales").status_code == 302
    assert client.get(path).status_code == 404
    with client.session_transaction() as s:
        sales_token = s["csrf"]
    assert (
        client.post(
            path, data={"csrf": sales_token, "version": 1, "decision": "approved"}
        ).status_code
        == 404
    )
    login("design")
    preview = client.get(path)
    assert "200.00" in preview.get_data(as_text=True) and not outbox
    form = {"csrf": token(preview), "version": 0, "decision": "approved"}
    assert client.post(path, data=form).status_code == 409 and not outbox
    form["version"] = 1
    assert client.post(path, data=form).status_code == 302
    assert outbox == [(employee, f"您的采购申请 #{ident}（显示器）已批准。")]
    assert outbox[0][1] in preview.get_data(as_text=True)
    assert client.post(path, data=form).status_code == 409 and len(outbox) == 1
    assert "已发送" in client.get(path).get_data(as_text=True)


def test_history_renders_previous_materials_and_only_authorized_mail(tmp_path):
    store = ProcurementStore(tmp_path / "history.sqlite")
    staff = {"design@example.test": "设计部", "sales@example.test": "销售部"}

    def inbound(mid, body, sender="design@example.test", subject="软件订阅申请"):
        return store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                subject,
                {"from": sender, "message_id": mid, "subject": subject, "email_thread": body},
            ),
            staff,
        )

    ident = inbound(
        "<history@test>", "采购对象：软件\n席位数：5\n业务用途：<script>alert(1)</script>"
    )
    inbound("<change@test>", "改成8席", subject=f"采购申请 #{ident}")
    foreign = inbound("<foreign@test>", "采购对象：销售部私有样例", sender="sales@example.test")
    client = create_app(
        store, {"design": {"department": "设计部"}}, lambda row, body: None
    ).test_client()
    with client.session_transaction() as session:
        session.update(manager="design", csrf="history-test")
    response = client.get(f"/requests/{ident}")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "材料版本历史" in page and "版本 1" in page and "版本 2" in page
    assert "收到的申请与补件" in page and "改成8席" in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "销售部私有样例" not in page
    assert client.get(f"/requests/{foreign}").status_code == 404
