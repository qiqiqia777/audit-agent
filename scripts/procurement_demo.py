"""Local, fictional manual acceptance portal. Outbound messages stay in SQLite."""

import argparse
import smtplib
import threading
from contextlib import closing
from pathlib import Path

from flask import abort, redirect, request, session
from werkzeug.security import generate_password_hash

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_mailbox import maintain_followups
from email_agent.procurement_web import create_app


def create_demo(directory):
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".demo-only"
    if (directory / "applications.sqlite").exists() and not marker.exists():
        raise ValueError("此目录已有非演示数据库，请选择独立演示目录")
    marker.write_text("fictional manual acceptance data", encoding="utf-8")
    store = ProcurementStore(directory / "applications.sqlite")
    staff = {
        "employee@example.test": "设计部",
        "sales@example.test": "销售部",
        "past@example.test": "设计部",
    }
    samples = [
        (
            "device",
            "employee@example.test",
            "设备采购申请",
            "采购对象：演示显示器\n业务用途：设计校色\n规格：27英寸\n数量：2\n报价：1200.55\n费用口径：单价",
        ),
        (
            "missing-purpose",
            "employee@example.test",
            "软件订阅申请",
            "采购对象：演示软件\n席位数：5\n订阅期限：12个月\n报价：120元/月\n费用口径：每席",
        ),
        (
            "software",
            "employee@example.test",
            "软件订阅申请",
            "采购对象：演示软件\n业务用途：出图\n席位数：5\n订阅期限：12个月\n报价：120元/月",
        ),
        (
            "foreign",
            "sales@example.test",
            "软件订阅申请",
            "采购对象：演示软件\n业务用途：销售部专用历史\n席位数：2\n订阅期限：12个月\n报价：100元/月\n费用口径：每席",
        ),
        (
            "past",
            "past@example.test",
            "软件订阅申请",
            "采购对象：演示软件\n业务用途：设计部历史出图\n席位数：1\n订阅期限：12个月\n报价：100元/月\n费用口径：每席",
        ),
    ]
    for key, label in [("ambiguous-a", "项目甲软件"), ("ambiguous-b", "项目乙软件")]:
        samples.append(
            (
                key,
                "employee@example.test",
                "软件订阅申请",
                f"采购对象：{label}\n业务用途：出图\n席位数：5\n订阅期限：12个月\n报价：120元/月",
            )
        )
    for key, sender, subject, body in samples:
        ident = store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                subject,
                {
                    "from": sender,
                    "subject": subject,
                    "message_id": f"<demo-{key}@example.test>",
                    "email_thread": body,
                },
            ),
            staff,
        )
        if key in {"past", "foreign"}:
            department = staff[sender]
            previous = store.detail(ident, department)
            if previous["decision"] is None:
                decided = store.decide(
                    ident, department, "demo-fixture", previous["version"], "approved"
                )
                attempt = store.claim_notification(
                    ident, department, "demo-fixture", decided["notification_attempts"][-1]["id"]
                )
                store.finish_notification(
                    attempt["id"],
                    "sent",
                    {
                        "message_id": f"<demo-history-{key}@example.test>",
                        "smtp_response": "seeded fictional history",
                    },
                )
    with closing(store.connect()) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS demo_outbox(
            id INTEGER PRIMARY KEY, application_id INTEGER, department TEXT, recipient TEXT, body TEXT)""")
    managers = {
        key: {"department": dept, "password_hash": generate_password_hash("demo-only")}
        for key, dept in [("design", "设计部"), ("sales", "销售部")]
    }

    def deliver(record, body):
        mode = session.get("demo_mode", "success")
        if mode == "failed":
            raise smtplib.SMTPRecipientsRefused({record["sender"]: (550, b"demo rejection")})
        if mode == "unknown":
            raise ConnectionResetError("controlled demo disconnect")
        with closing(store.connect()) as db, db:
            ident = db.execute(
                "INSERT INTO demo_outbox(application_id,department,recipient,body) VALUES(?,?,?,?)",
                (record["id"], record["department"], record["sender"], body),
            ).lastrowid
        return {
            "message_id": f"<demo-out-{ident}@example.test>",
            "smtp_response": "local demo outbox",
        }

    app = create_app(store, managers, deliver, wait_seconds=60)

    @app.after_request
    def banner(response):
        if response.mimetype == "text/html":
            csrf = session.get("csrf", "")
            selected_mode = {
                "success": "成功",
                "failed": "明确拒收",
                "unknown": "连接中断，结果未知",
            }.get(session.get("demo_mode", "success"), "成功")
            controls = f"""<aside style="padding:1rem;background:#fff3cd">
                手动验收 · 虚构资料 · 通知保存到本地演示收件箱
                <p>测试账号 design / sales，密码均为 demo-only。</p>
                <p>当前模拟发送结果：{selected_mode}</p>
                <a href="/demo/outbox">查看本部门演示收件箱</a> · <a href="/login">切换测试账号</a>
                <form method="post" action="/demo/mode"><input type="hidden" name="csrf" value="{csrf}">
                <label>下一次发送 <select name="mode"><option value="success">成功</option>
                <option value="failed">明确拒收</option><option value="unknown">连接中断，结果未知</option></select></label>
                <button>应用模拟结果</button></form>
                <form method="post" action="/demo/reply"><input type="hidden" name="csrf" value="{csrf}">
                <label>本部门申请编号（留空模拟归属不明） <input name="ident" type="number"></label>
                <label>模拟员工补件 <input name="body" value="每席位每月120元" required></label>
                <button>提交虚构回复</button></form></aside>"""
            response.set_data(
                response.get_data(as_text=True).replace("<main>", controls + "<main>", 1)
            )
        return response

    @app.post("/demo/mode")
    def mode():
        if request.form.get("mode") not in {"success", "failed", "unknown"}:
            abort(400)
        session["demo_mode"] = request.form["mode"]
        return redirect("/")

    @app.post("/demo/reply")
    def reply():
        if not request.form.get("ident"):
            department = managers[session["manager"]]["department"]
            sender = "employee@example.test" if department == "设计部" else "sales@example.test"
            event = Event(
                EventType.EMAIL_INBOUND,
                "补充采购材料",
                {"from": sender, "subject": "补充采购材料", "email_thread": request.form["body"]},
            )
            event.metadata["message_id"] = f"<demo-reply-{event.event_id}@example.test>"
            store.intake(event, staff)
            return redirect("/")
        try:
            ident = int(request.form["ident"])
            row = store.detail(ident, managers[session["manager"]]["department"])
        except (ValueError, LookupError):
            abort(404)
        if row["decision"]:
            abort(409)
        event = Event(
            EventType.EMAIL_INBOUND,
            f"采购申请 #{ident}",
            {
                "from": row["sender"],
                "subject": f"采购申请 #{ident}",
                "email_thread": request.form["body"],
            },
        )
        event.metadata["message_id"] = f"<demo-reply-{event.event_id}@example.test>"
        store.intake(event, staff)
        return redirect(f"/requests/{ident}")

    @app.get("/demo/outbox")
    def outbox():
        dept = managers[session["manager"]]["department"]
        with closing(store.connect()) as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM demo_outbox WHERE department=? ORDER BY id", (dept,)
                )
            ]
        return app.json.response(rows)

    return app, store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory", type=Path, default=Path("data/procurement-acceptance/manual-demo")
    )
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    app, store = create_demo(args.directory)
    stop = threading.Event()
    maintenance = threading.Thread(target=maintain_followups, args=(store, stop), daemon=True)
    maintenance.start()
    try:
        app.run(host="127.0.0.1", port=args.port)
    finally:
        stop.set()
        maintenance.join(timeout=5)


if __name__ == "__main__":
    main()
