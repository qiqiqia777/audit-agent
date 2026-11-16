"""Read-only presentation of the timestamps actually persisted by procurement."""

from datetime import datetime, timedelta, timezone


BEIJING = timezone(timedelta(hours=8))


def recorded_time(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def local_time(value):
    moment = recorded_time(value)
    return moment.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S") if moment else "未记录时间"


def history_events(record, followups):
    events = []

    def add(title, at, actor, version=None, note=""):
        events.append({"title": title, "at": at, "actor": actor, "version": version, "note": note})

    if record["decision"]:
        add(
            "批准申请" if record["decision"] == "approved" else "驳回申请",
            record["decided_at"],
            record["decided_by"],
        )
    for draft in followups:
        kind = "补件请求" if draft["kind"] == "request" else "催办"
        for attempt in draft["attempts"]:
            migrated = attempt["actor"] == "migration"
            add(
                f"旧{kind}记录迁入" if migrated else f"{kind}发送尝试 #{attempt['id']}",
                attempt["created_at"],
                None if migrated else attempt["actor"],
                draft["version"],
                (
                    "迁入记录创建时间；原操作者未记录，原发送时间见补件记录"
                    if draft["sent_at"] is not None
                    else "迁入记录创建时间；原发送时间与操作者未记录"
                )
                if migrated
                else "发送记录创建时间，不等同实际投递时间",
            )
            if attempt["verified_by"]:
                add(
                    f"核实{kind}发送结果",
                    attempt["verified_at"],
                    attempt["verified_by"],
                    draft["version"],
                )
    for attempt in record["notification_attempts"]:
        add(
            f"结果邮件发送尝试 #{attempt['id']}"
            if attempt["message_id"]
            else f"结果通知记录创建 #{attempt['id']}",
            attempt["created_at"],
            attempt["actor"] if attempt["message_id"] and attempt["actor"] != "migration" else None,
            note="发送记录创建时间，不等同实际投递时间"
            if attempt["message_id"]
            else "历史迁入或尚未发送的记录；原发送时间与操作者未记录",
        )
        if attempt["verified_by"]:
            add("核实结果邮件投递", attempt["verified_at"], attempt["verified_by"])
    return sorted(
        events,
        key=lambda event: (
            recorded_time(event["at"]) is None,
            recorded_time(event["at"]) or datetime.max.replace(tzinfo=timezone.utc),
        ),
    )
