"""Read-only material review for office equipment requests (CNY)."""

import re
from decimal import Decimal


POLICY_VERSION = "演示采购制度 v1.0"
CLAUSES = {
    "EQ-1": "设备申请须写明采购对象、业务用途、具体规格和正整数数量。",
    "EQ-2": "预计费用须为人民币正金额，精确到分，并标明为单件报价或整批总价。口径不清须先补件。",
}


def review_equipment(application: dict) -> dict:
    """Review structured materials supplied by the email application. No writes or mail."""
    questions = []
    summary = {}
    for field, label in (("item", "采购对象"), ("purpose", "业务用途"), ("spec", "规格")):
        value = application.get(field)
        if isinstance(value, str) and value.strip():
            summary[field] = value.strip()
        else:
            questions.append({"field": field, "question": f"请补充{label}。", "clause": "EQ-1"})

    quantity = application.get("quantity")
    if type(quantity) is int and quantity > 0:
        summary["quantity"] = quantity
    else:
        questions.append({"field": "quantity", "question": "请提供正整数数量。", "clause": "EQ-1"})

    amount = application.get("amount")
    basis = application.get("price_basis")
    # Parse decimal text from the source. Never guess a price basis from free text.
    if (
        isinstance(amount, (str, int, Decimal))
        and re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", str(amount))
        and Decimal(amount) > 0
    ):
        summary["amount"] = str(amount)
    else:
        questions.append({"field": "amount", "question": "请提供有效人民币报价，最多两位小数。", "clause": "EQ-2"})
    if basis in ("unit", "total"):
        summary["price_basis"] = basis
    else:
        questions.append({"field": "price_basis", "question": "报价为每件单价还是整批总价？", "clause": "EQ-2"})

    total = None
    if "amount" in summary and "price_basis" in summary and "quantity" in summary:
        whole, _, fraction = str(amount).partition(".")
        cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
        if basis == "unit":
            cents *= quantity
        total = f"{cents // 100}.{cents % 100:02d}"
    return {
        "status": "needs_clarification" if questions else "ready_for_review",
        "materials": summary,
        "estimated_total_cny": total,
        "questions": questions,
        "policy_version": POLICY_VERSION,
        "clauses": CLAUSES.copy(),
    }
