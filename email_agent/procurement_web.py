"""Local approval portal. Manager records in the roster hold Werkzeug password hashes."""

import argparse
import hmac
import json
import secrets
import smtplib
from contextlib import closing
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash

from email_agent.config import AppConfig
from email_agent.procurement import ProcurementStore
from email_agent.sending.smtp import send_email
from email_agent.sending.whitelist import is_allowed


DECISIONS = {"approved": "批准", "rejected": "驳回"}
STATES = {
    "pending": "待发送",
    "unknown": "发送结果待核实",
    "sent": "已发送",
    "failed": "通知发送失败",
}


def notice(record, decision):
    return f"您的采购申请 #{record['id']}（{record['materials'].get('item') or '采购事项'}）已{DECISIONS[decision]}。"


def create_app(store, managers, deliver):
    app = Flask(__name__)
    app.secret_key = secrets.token_bytes(32)
    app.config.update(SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=8192)

    def page(title, template, **values):
        return render_template_string(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{{title}}</title>'
            "<main><h1>{{title}}</h1>" + template + "</main></html>",
            title=title,
            states=STATES,
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
            {% for id in change.candidates %}<button name="ident" value="{{id}}">归入申请 #{{id}}</button>{% endfor %}</form>{% endfor %}""",
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
                choice = request.form.get("decision")
                record = store.decide(
                    ident, dept, manager, int(request.form.get("version", "")), choice
                )
                # A crash after claiming the send must leave a visible uncertain outcome.
                with closing(store.connect()) as db, db:
                    db.execute(
                        "UPDATE applications SET notification_status='unknown' WHERE id=?", (ident,)
                    )
                try:
                    deliver(record, notice(record, choice))
                    state = "sent"
                except (
                    smtplib.SMTPResponseException,
                    smtplib.SMTPRecipientsRefused,
                    PermissionError,
                ):
                    state = "failed"
                except (OSError, smtplib.SMTPException):
                    state = "unknown"
                with closing(store.connect()) as db, db:
                    db.execute(
                        "UPDATE applications SET notification_status=? WHERE id=?", (state, ident)
                    )
                return redirect(url_for("detail", ident=ident))
        except LookupError:
            abort(404)
        except ValueError as exc:
            return page(
                "申请需要重新核对", '<p>{{reason}}</p><a href="">查看最新申请</a>', reason=str(exc)
            ), 409
        return page(
            f"采购申请 #{ident}",
            """<a href="/">部门申请</a><p>申请人 {{r.sender}} · 版本 {{r.version}}</p>
            <dl>{% for k,label in labels.items() if k in r.materials %}<dt>{{label}}</dt><dd>{{r.materials.get(k,'待补充')}}</dd>{% endfor %}</dl>
            <p>预计总额 {{r.review.estimated_total_cny or '待核实'}} 元</p><h2>{{r.review.policy_version}}</h2>
            {% for k,v in r.review.clauses.items() %}<p>{{k}} · {{v}}</p>{% endfor %}
            {% for q in r.review.questions %}<p>{{q.question}}（{{q.clause}}）</p>{% endfor %}
            {% if r.changes %}<h2>材料变更</h2>{% for k,v in r.changes.items() %}<p>{{labels.get(k,k)}}：{{v[0]}} → {{v[1]}}</p>{% endfor %}{% endif %}
            {% if r.cases %}<h2>本部门已办结同类案例</h2>{% for c in r.cases %}<p><a href="{{url_for('detail',ident=c.id)}}">申请 #{{c.id}}</a> · {{'软件订阅' if c.category=='software' else '办公设备'}} · {{c.purpose}} · {{c.total}} 元 · {{decisions[c.decision]}}</p>{% endfor %}{% endif %}
            {% if r.decision %}<p>已{{decisions[r.decision]}} · {{r.decided_by}} · {{r.decided_at}} · {{states[r.notification_status]}}</p>
            {% else %}{% for choice,body in previews.items() %}<form method="post">
            <p>发给 {{r.sender}}：{{body}}</p><input type="hidden" name="csrf" value="{{session.csrf}}">
            <input type="hidden" name="version" value="{{r.version}}"><button name="decision" value="{{choice}}"
            {% if choice=='approved' and r.review.questions %}disabled{% endif %}>{{decisions[choice]}}并通知</button>
            </form>{% endfor %}{% endif %}""",
            r=record,
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
            subject=f"采购申请 #{record['id']} 处理结果",
            body=body,
            in_reply_to=reply,
            references=reply,
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
        ProcurementStore(directory / "applications.sqlite"), roster["managers"], smtp_delivery(cfg)
    )
    app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
