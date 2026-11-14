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


def review_subscription(application: dict) -> dict:
    """Review one software quote in CNY. Term is months; price is per billing period."""
    clauses = {
        "SW-1": "软件申请须说明采购对象、业务用途、正整数席位数和订阅期限。",
        "SW-2": "须明确报价金额、计费周期及报价覆盖单席还是全部席位；不足整周期时须明确实际收费。",
    }
    summary = {}
    questions = []
    def missing(field, question, clause):
        questions.append({"field": field, "question": question, "clause": clause})
    for field, label in (("item", "采购对象"), ("purpose", "业务用途")):
        value = application.get(field)
        if isinstance(value, str) and value.strip():
            summary[field] = value.strip()
        else:
            missing(field, f"请补充{label}。", "SW-1")
    for field, label in (("seats", "席位数"), ("months", "订阅月数")):
        value = application.get(field)
        if type(value) is int and value > 0:
            summary[field] = value
        else:
            missing(field, f"请提供正整数{label}。", "SW-1")
    price = str(application.get("amount", ""))
    if re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", price) and Decimal(price) > 0:
        summary["amount"] = price
    else:
        missing("amount", "请提供以元计的正金额，最多两位小数。", "SW-2")
    period = application.get("billing_period")
    if period in ("monthly", "quarterly", "yearly"):
        summary["billing_period"] = period
    else:
        missing("billing_period", "报价按月、季度还是年计费？", "SW-2")
    basis = application.get("price_basis")
    if basis in ("per_seat", "all_seats"):
        summary["price_basis"] = basis
    else:
        missing("price_basis", "报价是每席位价格，还是全部席位合计？", "SW-2")
    total = None
    if {"billing_period", "months"} <= summary.keys():
        periods, remainder = divmod(summary["months"], {"monthly": 1, "quarterly": 3, "yearly": 12}[period])
        if remainder:
            missing("billing_period", "期限不足整计费周期，请确认实际收费口径。", "SW-2")
        elif {"price_basis", "amount", "seats"} <= summary.keys():
            whole, _, fraction = price.partition(".")
            cents = (int(whole) * 100 + int(fraction.ljust(2, "0"))) * periods
            if basis == "per_seat":
                cents *= summary["seats"]
            total = f"{cents // 100}.{cents % 100:02d}"
    return {"status": "needs_clarification" if questions else "ready_for_review",
            "materials": summary, "estimated_total_cny": total, "questions": questions,
            "policy_version": POLICY_VERSION, "clauses": clauses}
