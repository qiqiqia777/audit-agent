"""One read-only selection path for department lists and mail exception queues."""

from math import ceil


TASKS = {
    "approve": "待我审批",
    "confirm_followup": "补件邮件待我确认",
    "verify_delivery": "邮件发送待核实",
    "retry_delivery": "邮件待恢复发送",
    "waiting_requester": "等待申请人补件",
}
CATEGORIES = {"software": "软件订阅", "equipment": "办公设备"}
DECISION_FILTERS = {"pending": "待审批", "approved": "已批准", "rejected": "已驳回"}
MAIL_FILTERS = {
    "none": "尚未生成",
    "pending": "待发送",
    "unknown": "结果邮件待核实",
    "failed": "结果邮件发送失败",
    "sent": "已发送",
}


def parse_filters(args):
    filters = {
        key: args.get(key, "").strip()
        for key in ("q", "category", "decision", "mail", "task", "view")
    }
    for key, allowed in (
        ("category", CATEGORIES),
        ("decision", DECISION_FILTERS),
        ("mail", MAIL_FILTERS),
        ("task", TASKS),
        ("view", {"all", "exceptions"}),
    ):
        if filters[key] and filters[key] not in allowed:
            raise ValueError(f"无效筛选项：{key}")
    if len(filters["q"]) > 200:
        raise ValueError("搜索内容不能超过200个字符")
    page = int(args.get("page", "1"))
    if page < 1:
        raise ValueError("页码须为正整数")
    return filters, page


def describe_request(row, followups):
    """Classify the next actor from persisted state, never create a followup."""
    active = [f for f in followups if not row["decision"] and not f["closed_at"]]
    unknown = any(f["state"] == "unknown" for f in active)
    failed = any(f["state"] == "failed" for f in active)
    draft = next((f for f in reversed(active) if f["state"] == "draft"), None)
    waiting = any(f["kind"] == "request" and f["state"] == "sent" for f in active)
    notification = row["notification_status"]
    task, anchor = "", ""
    if row["decision"] and notification == "unknown":
        task, anchor = "verify_delivery", "sending-records"
    elif unknown:
        task, anchor = "verify_delivery", "followup-records"
    elif row["decision"] and notification in ("failed", "pending"):
        task, anchor = "retry_delivery", "sending-records"
    elif failed:
        task, anchor = "retry_delivery", "followup-records"
    elif draft:
        task, anchor = "confirm_followup", "followup-records"
    elif waiting:
        task = "waiting_requester"
    elif not row["decision"] and row["review_state"] in (None, "completed"):
        if row["review"].get("questions"):
            task, anchor = "confirm_followup", "followup-records"
        else:
            task, anchor = "approve", "sending-records"
    if unknown:
        followup_label = "补件待核实"
    elif failed:
        followup_label = "补件发送失败"
    elif draft:
        followup_label = "催办待确认" if draft["kind"] == "reminder" else "补件待确认"
    elif waiting:
        followup_label = "等待申请人补件"
    elif task == "confirm_followup":
        followup_label = "材料待补充"
    else:
        followup_label = "无待处理补件"
    return row | {
        "item": row["materials"].get("item") or "采购事项待补充",
        "total": row["review"].get("estimated_total_cny"),
        "task": task,
        "task_label": TASKS.get(task, "查看详情"),
        "anchor": anchor,
        "followup_label": followup_label,
        "has_exception": notification in ("unknown", "failed", "pending") or unknown or failed,
    }


def matches_filters(row, filters):
    if filters.get("view") == "exceptions" and not row["has_exception"]:
        return False
    if filters.get("category") and row["category"] != filters["category"]:
        return False
    if filters.get("decision") and (row["decision"] or "pending") != filters["decision"]:
        return False
    if filters.get("mail") and (row["notification_status"] or "none") != filters["mail"]:
        return False
    if filters.get("task") and row["task"] != filters["task"]:
        return False
    text = " ".join(
        (str(row["id"]), row["item"], row["sender"], str(row["materials"].get("purpose", "")))
    ).casefold()
    return filters.get("q", "").casefold() in text


def select_requests(store, department, filters, page=1, page_size=20):
    rows, followups = store.listing_snapshot(department)
    summaries = [describe_request(row, followups.get(row["id"], [])) for row in rows]
    selected = [row for row in summaries if matches_filters(row, filters)]
    pages = max(1, ceil(len(selected) / page_size))
    page = min(page, pages)
    return {
        "rows": selected[(page - 1) * page_size : page * page_size],
        "total": len(selected),
        "department_total": len(rows),
        "page": page,
        "pages": pages,
    }
