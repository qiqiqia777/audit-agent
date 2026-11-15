"""Real self-mail + MiniHermes software procurement acceptance, using an isolated inbox cursor."""

import argparse
import json
import re
import time
import uuid
from pathlib import Path

from dotenv import dotenv_values
from imap_tools import AND, MailBox
from werkzeug.security import generate_password_hash

from email_agent.config import AppConfig
from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_web import create_app, smtp_delivery
from email_agent.procurement_worker import work_once
from email_agent.sending.smtp import send_email
from email_agent.sources.imap_poller import ImapPoller
from minihermes.config import Settings
from minihermes.loop.models import get_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--self-mail", action="store_true", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    cfg = AppConfig.from_env(args.env_file)
    if not cfg.imap or not cfg.smtp or cfg.imap.user.casefold() != cfg.smtp.user.casefold():
        raise SystemExit("需要同一账号自发自收")
    values = dotenv_values(args.env_file)
    settings = Settings(
        provider="openai",
        api_key=values.get("GLM_API_KEY") or "",
        base_url=values.get("GLM_BASE_URL"),
        model=values.get("GLM_MODEL") or "",
    )
    if not settings.api_key or not settings.base_url or not settings.model:
        raise SystemExit("需要 GLM 测试模型配置")
    args.directory.mkdir(parents=True, exist_ok=False)
    evidence = {"sample": uuid.uuid4().hex[:12], "model": settings.model}

    def save(name, value):
        evidence[name] = value
        (args.directory / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(name, value, flush=True)

    store = ProcurementStore(args.directory / "applications.sqlite", model_review=True)
    sent_samples = {}
    received_ids = {}

    class Inbox:
        def put(self, event):
            for original_id, (subject, body) in sent_samples.items():
                if event.metadata.get("subject") == subject and body.strip() in event.metadata.get(
                    "email_thread", ""
                ):
                    store.intake(event, {cfg.imap.user.casefold(): "演示部"})
                    received_ids[original_id] = event.metadata["message_id"]
                    break

    tag = evidence["sample"]
    save("mail_scope", "unique subject tag and exact self-sent sample body")

    class SampleClient:
        """Restrict the real server search to this fictional run's unique subjects."""

        def __enter__(self):
            self.box = MailBox(cfg.imap.host, port=cfg.imap.port, timeout=20).login(
                cfg.imap.user, cfg.imap.password, initial_folder=cfg.imap.folder
            )
            return self

        def __exit__(self, *exc):
            self.box.logout()

        def uids(self):
            return self.box.uids(AND(subject=tag), charset="UTF-8")

        def fetch(self, criteria, *, mark_seen=False):
            return [
                message
                for message in self.box.fetch(
                    AND(subject=tag), charset="UTF-8", mark_seen=mark_seen, reverse=True, limit=50
                )
                if tag in message.subject
            ]

    poller = ImapPoller(Inbox(), cfg.imap, args.directory, client_factory=SampleClient)
    poller.poll_once()
    model = get_client(settings)

    def send(subject, body, reply=None):
        receipt = send_email(
            host=cfg.smtp.host,
            port=cfg.smtp.port,
            user=cfg.smtp.user,
            password=cfg.smtp.password,
            from_addr=cfg.smtp.user,
            to=cfg.imap.user,
            subject=subject,
            body=body,
            in_reply_to=reply,
            references=reply,
        )
        mid = receipt["message_id"]
        sent_samples[mid] = (subject, body)
        save("self_mail_submitted", len(sent_samples))
        return mid

    def ingest(mid):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            poller.poll_once()
            if mid in received_ids:
                return received_ids[mid]
            time.sleep(4)
        raise TimeoutError("测试邮件未由 IMAP 入口接收")

    def review():
        assert work_once(store, model, settings.model)
        row = store.inbox("演示部")[0]
        report = store.detail(row["id"], "演示部")
        assert report["model_review"]["state"] == "completed", report["model_review"]
        return report

    def csrf(response):
        return re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))[1]

    receipts = []

    def deliver(row, body):
        receipt = smtp_delivery(cfg)(row, body)
        receipts.append(receipt)
        return receipt

    secret = uuid.uuid4().hex
    client = create_app(
        store,
        {"demo": {"department": "演示部", "password_hash": generate_password_hash(secret)}},
        deliver,
        wait_seconds=60,
    ).test_client()
    assert (
        client.post(
            "/login", data={"csrf": csrf(client.get("/login")), "user": "demo", "password": secret}
        ).status_code
        == 302
    )
    tag = evidence["sample"]
    initial = send(
        "软件订阅申请 " + tag,
        f"采购对象：演示软件-{tag}\n业务用途：虚构设计演示\n席位数：5\n订阅期限：12个月\n报价：120元/月",
    )
    ingest(initial)
    record = review()
    ident = record["id"]
    url = f"/requests/{ident}"
    assert record["review"]["estimated_total_cny"] is None
    assert "price_basis" in {q["field"] for q in record["review"]["questions"]}
    save("ambiguous_quote_requires_clarification", True)
    preview = client.get(url)
    (draft,) = store.followups(ident, "演示部", time.time())
    assert not receipts
    assert (
        client.post(url, data={"csrf": csrf(preview), "followup": draft["id"]}).status_code == 302
    )
    assert len(receipts) == 1
    request_mid = receipts[0]["message_id"]

    def received(mid, expected):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            with MailBox(cfg.imap.host, port=cfg.imap.port, timeout=20).login(
                cfg.imap.user, cfg.imap.password, initial_folder=cfg.imap.folder
            ) as box:
                for message in box.fetch(
                    AND(subject=f"采购申请 #{ident}"),
                    charset="UTF-8",
                    reverse=True,
                    limit=50,
                    mark_seen=False,
                ):
                    if (
                        expected in message.text
                        and tag in message.text
                        and message.from_.casefold() == cfg.imap.user.casefold()
                    ):
                        observed_id = message.headers["message-id"][0]
                        headers = message.headers.get("x-audit-message-id") or ()
                        store.intake(
                            Event(
                                EventType.EMAIL_INBOUND,
                                "",
                                {
                                    "from": message.from_,
                                    "message_id": observed_id,
                                    "audit_message_id": headers[0] if headers else "",
                                    "subject": message.subject,
                                    "email_thread": message.text,
                                },
                            ),
                            {cfg.imap.user.casefold(): "演示部"},
                        )
                        return observed_id
            time.sleep(4)
        raise TimeoutError("未找到与发送编号匹配的结果邮件")

    request_mid = received(request_mid, "报价是每席位")
    save("clarification_received", True)
    # Reply only to the outbound request ID, with no application number in subject.
    clarification = send("Re: 补充报价 " + tag, "每席位每月 120 元", request_mid)
    clarification = ingest(clarification)
    record = review()
    assert record["review"]["estimated_total_cny"] == "7200.00"
    save("clarified_total", "7200.00")
    old_version = record["version"]
    old_page = client.get(url)
    changed = send("Re: 修改席位 " + tag, "改成 8 席", clarification)
    ingest(changed)
    record = review()
    assert record["review"]["estimated_total_cny"] == "11520.00"
    assert (
        client.post(
            url, data={"csrf": csrf(old_page), "version": old_version, "decision": "approved"}
        ).status_code
        == 409
    )
    assert not store.detail(ident, "演示部")["decision"] and len(receipts) == 1
    save("stale_page_no_decision_or_send", True)
    current = client.get(url)
    assert "11520.00" in current.get_data(as_text=True)
    assert (
        client.post(
            url, data={"csrf": csrf(current), "version": record["version"], "decision": "approved"}
        ).status_code
        == 302
    )
    assert len(receipts) == 2
    received(receipts[-1]["message_id"], "已批准")
    save("approved_notice_received", True)
    save("final_total", "11520.00")


if __name__ == "__main__":
    main()
