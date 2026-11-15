"""Persist equipment applications from the purchasing mailbox."""

import json
import re
import sqlite3
from contextlib import closing
from email.utils import make_msgid, parseaddr
from pathlib import Path

from email_agent.events import Event, EventType


def equipment_fields(body: str) -> dict:
    """Read labelled lines from an employee's application email."""
    labels = {
        "采购对象": "item",
        "业务用途": "purpose",
        "规格": "spec",
        "数量": "quantity",
        "报价": "amount",
        "预计费用": "amount",
        "费用口径": "price_basis",
        "席位数": "seats",
        "订阅期限": "months",
        "计费周期": "billing_period",
    }
    fields = {}
    for line in body.splitlines():
        if line.startswith(">") or line.startswith("-----Original Message"):
            break
        parts = re.split(r"[:：]", line, maxsplit=1)
        if len(parts) != 2 or parts[0].strip() not in labels:
            continue
        key, value = labels[parts[0].strip()], parts[1].strip()
        if key == "months":
            value = value.removesuffix("个月")
        if key in {"quantity", "months", "seats"} and re.fullmatch(r"[0-9]{1,9}", value):
            value = int(value)
        elif key == "price_basis":
            value = {
                "单价": "unit",
                "每件单价": "unit",
                "总价": "total",
                "整批总价": "total",
                "每席": "per_seat",
                "全部席位": "all_seats",
            }.get(value, value)
        elif key == "billing_period":
            value = {"月": "monthly", "按月": "monthly", "季度": "quarterly", "年": "yearly"}.get(
                value, value
            )
        elif key == "amount":
            if value.endswith(("元/月", "元/年")):
                fields["billing_period"] = "monthly" if value.endswith("/月") else "yearly"
                value = value[:-2]
            value = value.removesuffix("元").strip()
        fields[key] = value
    fresh = "\n".join(re.split(r"^>|^-----Original Message", body, maxsplit=1, flags=re.M)[:1])
    price = re.search(r"(每席位|全部席位合计)每月\s*([0-9]+(?:\.[0-9]{1,2})?)\s*元", fresh)
    if price:
        fields.update(
            amount=price[2],
            billing_period="monthly",
            price_basis="per_seat" if price[1] == "每席位" else "all_seats",
        )
    seats = re.search(r"改(?:为|成)\s*([0-9]{1,9})\s*席", fresh)
    if seats:
        fields["seats"] = int(seats[1])
    return fields


class ProcurementStore:
    def __init__(self, path: Path):
        self.path = path
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS applications(
                    id INTEGER PRIMARY KEY,
                    inbound_key TEXT NOT NULL UNIQUE,
                    sender TEXT NOT NULL,
                    department TEXT NOT NULL,
                    materials TEXT NOT NULL,
                    review TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    decision TEXT,
                    decided_by TEXT,
                    decided_at TEXT,
                    notification_status TEXT
                );
                CREATE TABLE IF NOT EXISTS followups(
                    id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL, version INTEGER NOT NULL,
                    kind TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
                    sent_at REAL, due_at REAL, message_id TEXT, UNIQUE(application_id,version,kind)
                );
                CREATE TABLE IF NOT EXISTS incoming_changes(
                    mail_key TEXT PRIMARY KEY, sender TEXT, department TEXT, patch TEXT,
                    candidates TEXT, applied_to INTEGER, body TEXT
                );
                CREATE TABLE IF NOT EXISTS revisions(
                    application_id INTEGER, version INTEGER, materials TEXT, review TEXT,
                    PRIMARY KEY(application_id,version)
                );
                CREATE TABLE IF NOT EXISTS notification_attempts(
                    id INTEGER PRIMARY KEY,
                    application_id INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    body TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    message_id TEXT,
                    receipt TEXT,
                    verified_by TEXT,
                    verification_note TEXT,
                    verified_at TEXT
                );
            """)
            if "category" not in {r[1] for r in db.execute("PRAGMA table_info(applications)")}:
                db.execute(
                    "ALTER TABLE applications ADD COLUMN category TEXT NOT NULL DEFAULT 'equipment'"
                )
                db.commit()
            # Preserve decisions created by earlier versions, including uncertain sends.
            with db:
                for row in db.execute("""SELECT * FROM applications WHERE decision IS NOT NULL
                    AND NOT EXISTS(SELECT 1 FROM notification_attempts WHERE application_id=applications.id)""").fetchall():
                    db.execute(
                        """INSERT INTO notification_attempts
                        (application_id,actor,recipient,body,state) VALUES(?,?,?,?,?)""",
                        (
                            row["id"],
                            row["decided_by"] or "migration",
                            row["sender"],
                            result_notice(dict(row)),
                            row["notification_status"] or "unknown",
                        ),
                    )

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def intake(self, event: Event, staff: dict[str, str]) -> int | None:
        """staff maps registered mailbox addresses to their departments."""
        from minihermes.ops.procurement import review_equipment, review_subscription

        if event.event_type != EventType.EMAIL_INBOUND:
            return None
        meta = event.metadata
        sender = parseaddr(meta.get("from", ""))[1].casefold()
        subject = meta.get("subject", "")
        if sender not in staff:
            return None
        message_id = meta.get("message_id")
        if not message_id and not meta.get("uid"):
            raise ValueError("采购入站事件缺少 Message-ID 和邮箱 UID")
        key = "mid:" + message_id if message_id else "uid:" + str(meta["uid"])
        materials = equipment_fields(meta.get("email_thread", ""))
        department = staff[sender]
        refs = re.findall(
            r"<[^<>\s]+>", meta.get("references", "") + " " + meta.get("in_reply_to", "")
        )
        numbers = {int(n) for n in re.findall(r"申请\s*[#＃]\s*([0-9]{1,12})", subject)}
        category = (
            "equipment"
            if subject.startswith("设备采购申请")
            else "software"
            if subject.startswith("软件订阅申请")
            else None
        )
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM applications WHERE inbound_key=?", (key,)
            ).fetchone()
            if existing:
                return existing[0]
            change = db.execute(
                "SELECT applied_to FROM incoming_changes WHERE mail_key=?", (key,)
            ).fetchone()
            if change:
                return change[0]
            if category and not (refs or numbers):
                review = (review_subscription if category == "software" else review_equipment)(
                    materials
                )
                return db.execute(
                    """INSERT INTO applications(inbound_key,sender,department,materials,review,category)
                    VALUES(?,?,?,?,?,?)""",
                    (key, sender, department, json.dumps(materials), json.dumps(review), category),
                ).lastrowid
            if not materials:
                return None
            rows = db.execute(
                "SELECT id,inbound_key FROM applications WHERE sender=? AND department=? AND decision IS NULL ORDER BY id",
                (sender, department),
            ).fetchall()
            ref_keys = {"mid:" + ref for ref in refs}
            matched = {r["id"] for r in rows if r["inbound_key"] in ref_keys}
            for mid in ref_keys:
                previous = db.execute(
                    "SELECT applied_to FROM incoming_changes WHERE mail_key=? AND sender=? AND department=?",
                    (mid, sender, department),
                ).fetchone()
                if previous and previous[0]:
                    matched.add(previous[0])
            owned = {r["id"] for r in rows}
            if (numbers | matched) - owned:
                return None
            candidates = sorted((numbers | matched) & owned) if numbers or refs else sorted(owned)
            if not candidates:
                return None
            db.execute(
                "INSERT INTO incoming_changes VALUES(?,?,?,?,?,NULL,?)",
                (
                    key,
                    sender,
                    department,
                    json.dumps(materials),
                    json.dumps(candidates),
                    meta.get("email_thread", ""),
                ),
            )
            if len(candidates) == 1 and (numbers or matched):
                self._apply_change(db, key, candidates[0], department)
                return candidates[0]
            return None

    @staticmethod
    def _apply_change(db, key, ident, department):
        from minihermes.ops.procurement import review_equipment, review_subscription

        change = db.execute(
            "SELECT * FROM incoming_changes WHERE mail_key=? AND department=?", (key, department)
        ).fetchone()
        row = db.execute(
            "SELECT * FROM applications WHERE id=? AND department=?", (ident, department)
        ).fetchone()
        if (
            not change
            or not row
            or ident not in json.loads(change["candidates"])
            or row["sender"] != change["sender"]
        ):
            raise LookupError("未找到候选申请")
        if change["applied_to"] or row["decision"]:
            raise ValueError("补件已分配或申请已办结")
        db.execute(
            "UPDATE followups SET state='cancelled' WHERE application_id=? AND state='draft'",
            (ident,),
        )
        fields = json.loads(row["materials"]) | json.loads(change["patch"])
        if fields != json.loads(row["materials"]):
            review = (review_subscription if row["category"] == "software" else review_equipment)(
                fields
            )
            db.execute(
                "INSERT INTO revisions VALUES(?,?,?,?)",
                (ident, row["version"], row["materials"], row["review"]),
            )
            db.execute(
                "UPDATE applications SET materials=?, review=?, version=version+1 WHERE id=?",
                (json.dumps(fields), json.dumps(review), ident),
            )
        db.execute("UPDATE incoming_changes SET applied_to=? WHERE mail_key=?", (ident, key))

    def assign_change(self, key, ident, department):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._apply_change(db, key, ident, department)

    def followups(self, ident, department, now):
        """Materialize one request/reminder for the current reviewed version."""
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM applications WHERE id=? AND department=?", (ident, department)
            ).fetchone()
            if not row:
                raise LookupError("未找到本部门申请")
            questions = json.loads(row["review"])["questions"]
            if questions and not row["decision"]:
                request_text = f"请补充采购申请 #{ident} 的材料：" + " ".join(
                    q["question"] for q in questions
                )

                def draft(kind, body):
                    db.execute(
                        "INSERT OR IGNORE INTO followups(application_id,version,kind,body) VALUES(?,?,?,?)",
                        (ident, row["version"], kind, body),
                    )

                draft("request", request_text)
                due = db.execute(
                    "SELECT 1 FROM followups WHERE application_id=? AND version=? AND kind='request' AND state='sent' AND due_at<=?",
                    (ident, row["version"], now),
                ).fetchone()
                if due:
                    draft("reminder", "补件提醒：" + request_text)
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM followups WHERE application_id=? ORDER BY id", (ident,)
                )
            ]

    def claim_followup(self, ident, department, draft_id):
        with closing(self.connect()) as db, db:
            result = db.execute(
                """UPDATE followups SET state='unknown' WHERE id=? AND application_id=? AND state='draft'
                AND version=(SELECT version FROM applications WHERE id=? AND department=? AND decision IS NULL)""",
                (draft_id, ident, ident, department),
            )
            if not result.rowcount:
                raise ValueError("草稿已撤销、已发送或申请已更新")
            return dict(db.execute("SELECT * FROM followups WHERE id=?", (draft_id,)).fetchone())

    def finish_followup(self, draft_id, state, now, wait_seconds, message_id=None):
        with closing(self.connect()) as db, db:
            db.execute(
                """UPDATE followups SET state=?,sent_at=?,due_at=?,message_id=? WHERE id=? AND state='unknown'""",
                (
                    state,
                    now if state == "sent" else None,
                    now + wait_seconds if state == "sent" else None,
                    message_id,
                    draft_id,
                ),
            )

    def pending_changes(self, department):
        with closing(self.connect()) as db:
            return [
                dict(r) | {"candidates": json.loads(r["candidates"])}
                for r in db.execute(
                    "SELECT * FROM incoming_changes WHERE department=? AND applied_to IS NULL",
                    (department,),
                )
            ]

    def detail(self, application_id: int, department: str) -> dict:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM applications WHERE id=? AND department=?",
                (application_id, department),
            ).fetchone()
            if row is None:
                raise LookupError("未找到本部门申请")
            earlier = db.execute(
                "SELECT materials, review FROM revisions WHERE application_id=? ORDER BY version DESC LIMIT 1",
                (application_id,),
            ).fetchone()
            history = db.execute(
                """SELECT id,category,materials,review,decision FROM applications
                WHERE department=? AND category=? AND decision IS NOT NULL AND id!=? ORDER BY id DESC LIMIT 10""",
                (department, row["category"], application_id),
            ).fetchall()
        result = dict(row)
        for key in ("materials", "review"):
            result[key] = json.loads(result[key])
        result["cases"] = [
            {
                "id": h["id"],
                "category": h["category"],
                "purpose": json.loads(h["materials"]).get("purpose"),
                "total": json.loads(h["review"])["estimated_total_cny"],
                "decision": h["decision"],
            }
            for h in history
        ]
        result["changes"] = {}
        with closing(self.connect()) as db:
            result["notification_attempts"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM notification_attempts WHERE application_id=? ORDER BY id",
                    (application_id,),
                )
            ]
        if earlier:
            before = json.loads(earlier["materials"])
            after = result["materials"]
            result["changes"] = {
                k: (before.get(k), after.get(k))
                for k in sorted(before.keys() | after.keys())
                if before.get(k) != after.get(k)
            }
            old_total = json.loads(earlier["review"])["estimated_total_cny"]
            if old_total != result["review"]["estimated_total_cny"]:
                result["changes"]["预计总额"] = (old_total, result["review"]["estimated_total_cny"])
        return result

    def inbox(self, department: str) -> list[dict]:
        with closing(self.connect()) as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,sender,version,decision,notification_status FROM applications "
                    "WHERE department=? ORDER BY id DESC",
                    (department,),
                )
            ]

    def decide(
        self, application_id: int, department: str, manager: str, version: int, decision: str
    ) -> dict:
        """Persist the reviewed decision before the caller attempts delivery."""
        if decision not in {"approved", "rejected"}:
            raise ValueError("请选择批准或驳回")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM applications WHERE id=? AND department=?",
                (application_id, department),
            ).fetchone()
            if row is None:
                raise LookupError("未找到本部门申请")
            if row["version"] != version or row["decision"]:
                raise ValueError("申请已更新或已决定，请查看最新记录")
            if decision == "approved" and json.loads(row["review"])["status"] != "ready_for_review":
                raise ValueError("材料尚待补齐")
            db.execute(
                """UPDATE applications SET decision=?, decided_by=?, decided_at=CURRENT_TIMESTAMP,
                          notification_status='pending' WHERE id=?""",
                (decision, manager, application_id),
            )
            decided = dict(row) | {"decision": decision}
            db.execute(
                """INSERT INTO notification_attempts
                (application_id,actor,recipient,body,state) VALUES(?,?,?,?,'pending')""",
                (application_id, manager, row["sender"], result_notice(decided)),
            )
        return self.detail(application_id, department)

    def claim_notification(self, ident, department, manager, attempt_id):
        """Atomically claim the expected pending attempt or retry a confirmed failure."""
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            application = db.execute(
                "SELECT * FROM applications WHERE id=? AND department=?", (ident, department)
            ).fetchone()
            if application is None:
                raise LookupError("未找到本部门申请")
            previous = db.execute(
                "SELECT * FROM notification_attempts WHERE application_id=? ORDER BY id DESC LIMIT 1",
                (ident,),
            ).fetchone()
            if (
                not previous
                or previous["id"] != attempt_id
                or previous["state"] not in ("pending", "failed")
            ):
                raise ValueError("发送记录已变化，请查看最新状态；待核实结果须先人工核实")
            if previous["state"] == "failed":
                attempt_id = db.execute(
                    """INSERT INTO notification_attempts
                    (application_id,actor,recipient,body,state) VALUES(?,?,?,?,'unknown')""",
                    (ident, manager, previous["recipient"], previous["body"]),
                ).lastrowid
            else:
                db.execute(
                    "UPDATE notification_attempts SET state='unknown' WHERE id=?", (attempt_id,)
                )
            db.execute(
                "UPDATE notification_attempts SET message_id=? WHERE id=?",
                (make_msgid(domain="audit-agent.local"), attempt_id),
            )
            db.execute("UPDATE applications SET notification_status='unknown' WHERE id=?", (ident,))
            return dict(
                db.execute(
                    "SELECT * FROM notification_attempts WHERE id=?", (attempt_id,)
                ).fetchone()
            )

    def finish_notification(self, attempt_id, state, receipt):
        if state not in ("sent", "failed", "unknown"):
            raise ValueError("无效发送结果")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            attempt = db.execute(
                "SELECT * FROM notification_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if not attempt or attempt["state"] != "unknown" or attempt["verified_at"]:
                return
            db.execute(
                """UPDATE notification_attempts SET state=?,message_id=COALESCE(?,message_id),receipt=?,completed_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (
                    state,
                    receipt.get("message_id"),
                    json.dumps(receipt, ensure_ascii=False),
                    attempt_id,
                ),
            )
            db.execute(
                "UPDATE applications SET notification_status=? WHERE id=?",
                (state, attempt["application_id"]),
            )

    def verify_notification(self, ident, department, manager, attempt_id, delivered, note):
        if delivered not in ("yes", "no") or not note.strip():
            raise ValueError("请填写核实结果和依据")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM applications WHERE id=? AND department=?", (ident, department)
            ).fetchone()
            if row is None:
                raise LookupError("未找到本部门申请")
            latest = db.execute(
                "SELECT * FROM notification_attempts WHERE application_id=? ORDER BY id DESC LIMIT 1",
                (ident,),
            ).fetchone()
            if not latest or latest["id"] != attempt_id or latest["state"] != "unknown":
                raise ValueError("发送记录已变化")
            state = "sent" if delivered == "yes" else "failed"
            db.execute(
                """UPDATE notification_attempts SET state=?,verified_by=?,verification_note=?,
                verified_at=CURRENT_TIMESTAMP WHERE id=?""",
                (state, manager, note.strip(), attempt_id),
            )
            db.execute("UPDATE applications SET notification_status=? WHERE id=?", (state, ident))


def result_notice(record):
    decision = {"approved": "批准", "rejected": "驳回"}[record["decision"]]
    materials = record["materials"]
    if isinstance(materials, str):
        materials = json.loads(materials)
    return f"您的采购申请 #{record['id']}（{materials.get('item') or '采购事项'}）已{decision}。"
