"""Explicit self-mail acceptance run. Uses an isolated DB and matches the sample by sender, subject and unique body marker."""

import argparse
import json
import re
import time
import uuid

from imap_tools import AND, MailBox
from werkzeug.security import generate_password_hash

from email_agent.config import AppConfig
from email_agent.procurement import ProcurementStore
from email_agent.procurement_mailbox import ProcurementInbox
from email_agent.procurement_web import create_app, smtp_delivery
from email_agent.sending.smtp import send_email
from email_agent.sources.imap_poller import ImapPoller


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-mail", required=True, action="store_true")
    parser.add_argument("--resume-inbound", help="reuse the exact already sent sample tag")
    args = parser.parse_args()
    cfg = AppConfig.from_env(".env")
    if not cfg.smtp or not cfg.imap or cfg.smtp.user.casefold() != cfg.imap.user.casefold():
        raise SystemExit("A configured self-mail test account is required")
    tag = args.resume_inbound or uuid.uuid4().hex[:12]
    if not re.fullmatch("[0-9a-f]{12}", tag):
        raise ValueError("invalid sample tag")
    directory = cfg.data_dir / "procurement-acceptance" / tag
    directory.mkdir(parents=True, exist_ok=bool(args.resume_inbound))
    if (directory / "applications.sqlite").exists():
        raise ValueError("sample already processed")
    evidence = {"sample": tag}

    def record(key, value):
        evidence[key] = value
        (directory / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(key, value, flush=True)

    def receive(subject, expected_body):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            with MailBox(cfg.imap.host, port=cfg.imap.port, timeout=20).login(
                cfg.imap.user, cfg.imap.password, initial_folder=cfg.imap.folder
            ) as box:
                for message in box.fetch(
                    AND(from_=cfg.imap.user, subject=subject),
                    charset="UTF-8",
                    reverse=True,
                    mark_seen=False,
                ):
                    if (
                        message.subject == subject
                        and expected_body in message.text
                        and message.from_.casefold() == cfg.imap.user.casefold()
                    ):
                        return message
            time.sleep(4)
        raise TimeoutError("No matching self-mail found before deadline")

    item = "演示显示器-" + tag
    if not args.resume_inbound:
        send_email(
            host=cfg.smtp.host,
            port=cfg.smtp.port,
            user=cfg.smtp.user,
            password=cfg.smtp.password,
            from_addr=cfg.smtp.user,
            to=cfg.smtp.user,
            subject="设备采购申请 " + tag,
            body=f"采购对象：{item}\n业务用途：演示校色\n规格：27英寸\n数量：2\n报价：1200.55\n费用口径：单价",
        )
        record("application_smtp_accepted", True)
    message = receive("设备采购申请 " + tag, item)
    store = ProcurementStore(directory / "applications.sqlite")
    inbox = ProcurementInbox(store, {cfg.imap.user.casefold(): "演示部"})
    ImapPoller(inbox, cfg.imap, directory)._emit_email(message, message.headers["message-id"][0])
    (application,) = store.inbox("演示部")
    ident = application["id"]
    assert store.detail(ident, "演示部")["review"]["estimated_total_cny"] == "2401.10"
    record("matched_inbound_and_total", "2401.10")
    password = uuid.uuid4().hex
    receipts = []

    def deliver(row, body):
        receipts.append(smtp_delivery(cfg)(row, body))

    client = create_app(
        store,
        {"demo": {"department": "演示部", "password_hash": generate_password_hash(password)}},
        deliver,
    ).test_client()

    def csrf(response):
        return re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))[1]

    assert (
        client.post(
            "/login",
            data={"csrf": csrf(client.get("/login")), "user": "demo", "password": password},
        ).status_code
        == 302
    )
    url = f"/requests/{ident}"
    preview = client.get(url)
    assert item in preview.get_data(as_text=True)
    assert (
        client.post(
            url, data={"csrf": csrf(preview), "decision": "approved", "version": "1"}
        ).status_code
        == 302
    )
    record("decision", store.detail(ident, "演示部")["decision"])
    if not receipts:
        raise RuntimeError(
            "Notification not confirmed sent; inspect local decision state before retry"
        )
    notification = receive(f"采购申请 #{ident} 处理结果", item)
    assert item in notification.text and "已批准" in notification.text
    record("matching_result_received", True)


if __name__ == "__main__":
    main()
