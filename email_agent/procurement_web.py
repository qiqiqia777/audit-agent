"""Local approval portal. Manager records in the roster hold Werkzeug password hashes."""

import argparse
import hmac
import json
import os
import time
import secrets
import smtplib
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, redirect, render_template, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash

from email_agent.config import AppConfig
from email_agent.procurement import ProcurementStore, result_notice
from email_agent.procurement_presentation import history_events, local_time
from email_agent.sending.smtp import send_email
from email_agent.sending.whitelist import is_allowed


DECISIONS = {"approved": "批准", "rejected": "驳回"}
STATES = {
    "pending": "待发送",
    "unknown": "发送结果待核实",
    "sent": "已发送",
    "failed": "通知发送失败",
    "draft": "待确认",
    "cancelled": "已撤销",
}
REVIEW_STATES = {
    "pending": "待处理",
    "running": "正在审查",
    "completed": "已完成",
    "failed": "未通过",
    "superseded": "已被新版本替代",
}


def notice(record, decision):
    return result_notice(record | {"decision": decision})


def create_app(store, managers, deliver, wait_seconds=48 * 3600):
    if wait_seconds <= 0:
        raise ValueError("补件等待时间须为正数")
    app = Flask(__name__)
    app.jinja_env.filters["local_time"] = local_time
    app.secret_key = secrets.token_bytes(32)
    app.config.update(SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=8192)

    def page(title, template, **values):
        return render_template_string(
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>{{title}}</title><style>body{font-family:Inter,"Microsoft Yahei",sans-serif;color:#172332;background:#f7f8fa}'
            "main{max-width:960px;margin:2rem auto;padding:1.5rem;background:white;border-radius:12px}"
            "h1{font-size:1.7rem}h2{font-size:1.2rem;margin-top:2rem}dt{font-weight:600;margin-top:.6rem}"
            "button,input{font:inherit;margin:.4rem;padding:.6rem}button{cursor:pointer}button:disabled{cursor:default}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:1rem;background:#f2f4f7}details{margin:1rem 0}"
            "form{padding:.6rem;border:1px solid #dce2e8;border-radius:6px;margin:1rem 0}a{color:#155a9c}"
            "</style></head><body><main><h1>{{title}}</h1>" + template + "</main></body></html>",
            title=title,
            states=STATES,
            review_states=REVIEW_STATES,
            decisions=DECISIONS,
            **values,
        )

    @app.before_request
    def authorize():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        if request.method == "POST" and not hmac.compare_digest(
            request.form.get("csrf", "").encode(), session["csrf"].encode()
        ):
            abort(403)
        if request.endpoint != "login" and session.get("manager") not in managers:
            return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user = request.form.get("user", "")
            if user not in managers or not check_password_hash(
                managers[user]["password_hash"], request.form.get("password", "")
            ):
                abort(403)
            session.clear()
            session.update(manager=user, csrf=secrets.token_urlsafe(32))
            return redirect(url_for("inbox"))
        return page(
            "负责人登录",
            """<form method="post"><input type="hidden" name="csrf" value="{{session.csrf}}">
            <label>账号 <input name="user" required></label><label>密码 <input type="password" name="password" required></label>
            <button>登录</button></form>""",
        )

    @app.get("/")
    def inbox():
        rows = store.inbox(managers[session["manager"]]["department"])
        return page(
            "部门采购申请",
            """<ul>{% for r in rows %}<li>
            <a href="{{url_for('detail', ident=r.id)}}">申请 #{{r.id}}</a> · {{r.sender}} ·
            {{decisions.get(r.decision,'待审批')}} {{states.get(r.notification_status,'')}}</li>
            {% else %}<li>暂无申请</li>{% endfor %}</ul>{% for change in changes %}<form method="post" action="/assign">
            <h2>补件归属待确认</h2><p>{{change.sender}} · {{change.body}}</p>
            <input type="hidden" name="csrf" value="{{session.csrf}}"><input type="hidden" name="key" value="{{change.mail_key}}">
            {% for id in change.candidates %}<p><a href="{{url_for('detail',ident=id)}}">查看候选申请 #{{id}}</a>
            <button name="ident" value="{{id}}">归入申请 #{{id}}</button></p>{% endfor %}</form>{% endfor %}""",
            rows=rows,
            changes=store.pending_changes(managers[session["manager"]]["department"]),
        )

    @app.post("/assign")
    def assign():
        try:
            store.assign_change(
                request.form["key"],
                int(request.form["ident"]),
                managers[session["manager"]]["department"],
            )
        except LookupError:
            abort(404)
        except ValueError:
            abort(409)
        return redirect(url_for("inbox"))

    @app.route("/requests/<int:ident>", methods=["GET", "POST"])
    def detail(ident):
        manager = session["manager"]
        dept = managers[manager]["department"]
        try:
            record = store.detail(ident, dept)
            if request.method == "POST":
                if "verify_followup" in request.form:
                    actual = request.form.get("sent_at", "").strip()
                    try:
                        sent_at = datetime.fromisoformat(actual).timestamp() if actual else None
                    except (OSError, OverflowError) as exc:
                        raise ValueError("请填写有效的实际发出时间") from exc
                    store.verify_followup(
                        ident,
                        dept,
                        int(request.form["verify_followup"]),
                        int(request.form["followup_attempt"]),
                        manager,
                        request.form.get("delivered"),
                        request.form.get("note", ""),
                        time.time(),
                        sent_at,
                    )
                    return redirect(url_for("detail", ident=ident))
                if "recheck" in request.form:
                    store.request_recheck(ident, dept, int(request.form["version"]))
                    return redirect(url_for("detail", ident=ident))
                if "followup" in request.form:
                    with store.delivery_lock("followup", int(request.form["followup"])):
                        expected = request.form.get("followup_attempt")
                        draft = store.claim_followup(
                            ident,
                            dept,
                            int(request.form["followup"]),
                            manager,
                            int(expected) if expected else None,
                            wait_seconds,
                        )
                        receipt = {}
                        try:
                            receipt = (
                                deliver(
                                    dict(
                                        record,
                                        mail_kind="补件",
                                        outbound_message_id=draft["message_id"],
                                    ),
                                    draft["body"],
                                )
                                or {}
                            )
                            status = "sent"
                        except (
                            smtplib.SMTPResponseException,
                            smtplib.SMTPRecipientsRefused,
                            PermissionError,
                        ) as exc:
                            receipt = {
                                "error_type": type(exc).__name__,
                                "smtp_code": getattr(exc, "smtp_code", None),
                            }
                            status = "failed"
                        except (OSError, smtplib.SMTPException) as exc:
                            receipt = {"error_type": type(exc).__name__}
                            status = "unknown"
                        store.finish_followup(
                            draft["id"],
                            status,
                            time.time(),
                            wait_seconds,
                            receipt.get("message_id"),
                            attempt_id=draft["attempt_id"],
                            receipt=receipt,
                        )
                        return redirect(url_for("detail", ident=ident))
                if "verify" in request.form:
                    store.verify_notification(
                        ident,
                        dept,
                        manager,
                        int(request.form["attempt"]),
                        request.form["verify"],
                        request.form.get("note", ""),
                    )
                    return redirect(url_for("detail", ident=ident))
                with store.delivery_lock("notification", ident):
                    if "retry" not in request.form:
                        choice = request.form.get("decision")
                        record = store.decide(
                            ident, dept, manager, int(request.form.get("version", "")), choice
                        )
                        attempt_id = record["notification_attempts"][-1]["id"]
                    else:
                        attempt_id = int(request.form["attempt"])
                    attempt = store.claim_notification(ident, dept, manager, attempt_id)
                    receipt = {}
                    try:
                        receipt = (
                            deliver(
                                record | {"outbound_message_id": attempt["message_id"]},
                                attempt["body"],
                            )
                            or {}
                        )
                        state = "sent"
                    except (
                        smtplib.SMTPResponseException,
                        smtplib.SMTPRecipientsRefused,
                        PermissionError,
                    ) as exc:
                        receipt = {
                            "error_type": type(exc).__name__,
                            "smtp_code": getattr(exc, "smtp_code", None),
                        }
                        state = "failed"
                    except (OSError, smtplib.SMTPException) as exc:
                        receipt = {"error_type": type(exc).__name__}
                        state = "unknown"
                    store.finish_notification(attempt["id"], state, receipt)
                    return redirect(url_for("detail", ident=ident))
        except LookupError:
            abort(404)
        except ValueError as exc:
            return page(
                "申请需要重新核对", '<p>{{reason}}</p><a href="">查看最新申请</a>', reason=str(exc)
            ), 409
        followups = store.followups(ident, dept, time.time())
        return render_template(
            "procurement/detail.html",
            title=f"采购申请 #{ident}",
            states=STATES,
            review_states=REVIEW_STATES,
            decisions=DECISIONS,
            department=dept,
            timeline=history_events(record, followups),
            required_clause_ids=set(record["review"].get("cited_clause_ids", []))
            | {question["clause"] for question in record["review"]["questions"]},
            r=record,
            followups=followups,
            previews={c: notice(record, c) for c in DECISIONS},
            labels={
                "item": "采购对象",
                "purpose": "业务用途",
                "spec": "规格",
                "quantity": "数量",
                "amount": "报价",
                "seats": "席位数",
                "months": "订阅月数",
                "billing_period": "计费周期",
                "price_basis": "费用口径",
            },
        )

    return app


def smtp_delivery(cfg):
    def deliver(record, body):
        smtp = cfg.smtp
        if smtp is None or not is_allowed(record["sender"], cfg.send_whitelist):
            raise PermissionError("请核对测试邮箱及发件白名单")
        reply = (
            record["inbound_key"].removeprefix("mid:")
            if record["inbound_key"].startswith("mid:")
            else None
        )
        return send_email(
            host=smtp.host,
            port=smtp.port,
            user=smtp.user,
            password=smtp.password,
            from_addr=smtp.user,
            to=record["sender"],
            subject=f"采购申请 #{record['id']} {record.get('mail_kind', '处理结果')}",
            body=body,
            in_reply_to=reply,
            references=reply,
            message_id=record.get("outbound_message_id"),
        )

    return deliver


def main():
    parser = argparse.ArgumentParser(description="本机采购审批页面")
    parser.add_argument("--roster", required=True, type=Path)
    parser.add_argument("--env-file")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    cfg = AppConfig.from_env(args.env_file)
    roster = json.loads(args.roster.read_text(encoding="utf-8"))
    directory = cfg.data_dir / "procurement"
    directory.mkdir(parents=True, exist_ok=True)
    app = create_app(
        ProcurementStore(directory / "applications.sqlite", model_review=True),
        roster["managers"],
        smtp_delivery(cfg),
        wait_seconds=int(os.getenv("PROCUREMENT_WAIT_SECONDS", "172800")),
    )
    app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
