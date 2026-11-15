import re

from scripts.procurement_demo import create_demo


def test_same_software_history_keeps_current_purpose_required_and_department_private(tmp_path):
    app, store = create_demo(tmp_path)
    client = app.test_client()

    def login(user):
        page = client.get("/login").get_data(as_text=True)
        token = re.search('name="csrf" value="([^"]+)"', page)[1]
        assert (
            client.post(
                "/login", data={"csrf": token, "user": user, "password": "demo-only"}
            ).status_code
            == 302
        )
        with client.session_transaction() as session:
            return session["csrf"]

    token = login("design")
    records = [store.detail(r["id"], "设计部") for r in store.inbox("设计部")]
    current = next(
        r
        for r in records
        if r["materials"].get("item") == "演示软件" and not r["materials"].get("purpose")
    )
    history = next(
        r
        for r in records
        if r["decision"] == "approved" and r["materials"].get("item") == "演示软件"
    )
    url = f"/requests/{current['id']}"
    page = client.get(url).get_data(as_text=True)
    assert "设计部历史出图" in page and "销售部专用历史" not in page
    assert f"/requests/{history['id']}" in page
    assert "请补充业务用途" in page
    assert re.search(r'<button[^>]*value="approved"\s+disabled', page)
    assert client.get(f"/requests/{history['id']}").status_code == 200
    assert (
        client.post(
            url, data={"csrf": token, "version": current["version"], "decision": "approved"}
        ).status_code
        == 409
    )
    assert store.detail(current["id"], "设计部")["decision"] is None
    assert client.get("/demo/outbox").json == []

    token = login("sales")
    inbox = client.get("/").get_data(as_text=True)
    assert f'href="{url}"' not in inbox
    assert client.get(url).status_code == 404
    assert client.get(f"/requests/{history['id']}").status_code == 404
    assert (
        client.post(
            url, data={"csrf": token, "version": current["version"], "decision": "approved"}
        ).status_code
        == 404
    )
    assert client.get("/demo/outbox").json == []


def test_manual_demo_supports_confirmation_recovery_and_department_isolation(tmp_path):
    app, store = create_demo(tmp_path)
    client = app.test_client()

    def csrf(page):
        return re.search('name="csrf" value="([^"]+)"', page.get_data(as_text=True))[1]

    assert (
        client.post(
            "/login",
            data={"csrf": csrf(client.get("/login")), "user": "design", "password": "demo-only"},
        ).status_code
        == 302
    )
    with client.session_transaction() as session:
        token = session["csrf"]
    rows = store.inbox("设计部")
    device = next(
        r["id"] for r in rows if store.detail(r["id"], "设计部")["category"] == "equipment"
    )
    url = f"/requests/{device}"
    assert client.get("/demo/outbox").json == []
    assert client.post("/demo/mode", data={"csrf": token, "mode": "failed"}).status_code == 302
    assert (
        client.post(url, data={"csrf": token, "version": 1, "decision": "approved"}).status_code
        == 302
    )
    record = store.detail(device, "设计部")
    assert record["notification_status"] == "failed"
    assert client.get("/demo/outbox").json == []
    assert client.post("/demo/mode", data={"csrf": token, "mode": "success"}).status_code == 302
    attempt = record["notification_attempts"][-1]["id"]
    assert (
        client.post(url, data={"csrf": token, "retry": "", "attempt": attempt}).status_code == 302
    )
    outbox = client.get("/demo/outbox").json
    assert len(outbox) == 1 and outbox[0]["recipient"] == "employee@example.test"
    foreign = store.inbox("销售部")[0]["id"]
    assert client.get(f"/requests/{foreign}").status_code == 404
    assert (
        client.post(
            "/demo/reply", data={"csrf": token, "ident": foreign, "body": "改成8席"}
        ).status_code
        == 404
    )
    software = next(
        r["id"]
        for r in rows
        if not r["decision"]
        and store.detail(r["id"], "设计部")["materials"].get("item") == "演示软件"
    )
    page = client.get(f"/requests/{software}").get_data(as_text=True)
    assert "设计部历史出图" in page and "销售部专用历史" not in page
    assert (
        client.post(
            "/demo/reply", data={"csrf": token, "ident": software, "body": "每席位每月120元"}
        ).status_code
        == 302
    )
    assert store.detail(software, "设计部")["review"]["estimated_total_cny"] == "7200.00"
    assert (
        client.post(
            "/demo/reply", data={"csrf": token, "ident": software, "body": "改成8席"}
        ).status_code
        == 302
    )
    assert store.detail(software, "设计部")["review"]["estimated_total_cny"] == "11520.00"
    before = {r["id"]: store.detail(r["id"], "设计部")["materials"] for r in store.inbox("设计部")}
    assert (
        client.post("/demo/reply", data={"csrf": token, "ident": "", "body": "改成9席"}).status_code
        == 302
    )
    (change,) = store.pending_changes("设计部")
    assert len(change["candidates"]) >= 2
    assert all(
        store.detail(ident, "设计部")["materials"] == materials
        for ident, materials in before.items()
    )
    selected = change["candidates"][0]
    assert (
        client.post(
            "/assign", data={"csrf": token, "key": change["mail_key"], "ident": selected}
        ).status_code
        == 302
    )
    assert store.detail(selected, "设计部")["materials"]["seats"] == 9
    assert all(
        store.detail(ident, "设计部")["materials"] == materials
        for ident, materials in before.items()
        if ident != selected
    )
