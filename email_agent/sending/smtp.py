"""SMTP 发送（R7.1）：真实发送并保留 250 回执。

主证据链（G8）：SMTP 250 回执 + 发送后 IMAP 收件箱拉到该邮件；
Sent 文件夹是服务商行为，仅作次级观察项（docs/04 G8）。
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid


def _domain(addr: str) -> str:
    return addr.split("@")[-1] if "@" in addr else "localhost"


def send_email(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: str | None = None,
    message_id: str | None = None,
    timeout: float = 30.0,
    factory=smtplib.SMTP_SSL,
) -> dict:
    """发送邮件，返回 {message_id, smtp_response}。factory 可注入用于测试。"""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = message_id or make_msgid(domain=_domain(from_addr))
    msg["X-Audit-Message-ID"] = str(msg["Message-ID"])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)

    accepted = False
    try:
        with factory(host, port, timeout=timeout) as smtp:
            smtp.login(user, password)
            refused = smtp.send_message(msg)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            accepted = True
    except (OSError, smtplib.SMTPException):
        # A disconnect during QUIT cannot undo a completed DATA transaction.
        if not accepted:
            raise
    return {"message_id": str(msg["Message-ID"]), "smtp_response": "DATA accepted"}
