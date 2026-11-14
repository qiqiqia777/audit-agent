from copy import deepcopy
from decimal import Decimal

import pytest

from minihermes.ops.procurement import review_equipment


def equipment(**changes):
    return dict({"item": "显示器", "purpose": "设计校色", "spec": "27 英寸",
                 "quantity": 2, "amount": "1200.55", "price_basis": "unit"}, **changes)


@pytest.mark.parametrize(("basis", "total"), [("unit", "2401.10"), ("total", "1200.55")])
def test_complete_request_reports_ready_and_cites_policy(basis, total):
    report = review_equipment(equipment(price_basis=basis))
    assert report["status"] == "ready_for_review"
    assert report["estimated_total_cny"] == total
    assert report["materials"]["spec"] == "27 英寸"
    assert report["questions"] == []
    assert report["policy_version"] and report["clauses"]["EQ-2"]


def test_missing_materials_list_each_question_and_source():
    report = review_equipment({})
    assert report["status"] == "needs_clarification"
    assert {q["field"] for q in report["questions"]} == {
        "item", "purpose", "spec", "quantity", "amount", "price_basis"
    }
    assert all(q["clause"] in report["clauses"] for q in report["questions"])
    assert report["estimated_total_cny"] is None


@pytest.mark.parametrize(("field", "value"), [
    ("price_basis", None), ("quantity", True), ("quantity", 0),
    ("amount", "NaN"), ("amount", "120 元/件"), ("amount", "-1"), ("amount", "1.555"),
    ("amount", True), ("amount", 1200.55), ("amount", "0"),
    ("amount", Decimal("Infinity")), ("quantity", 2.0), ("quantity", -1),
    ("item", " "), ("purpose", None), ("spec", []),
])
def test_invalid_materials_require_clarification(field, value):
    report = review_equipment(equipment(**{field: value}))
    assert report["status"] == "needs_clarification"
    assert [q["field"] for q in report["questions"]] == [field]
    expected_total = "2401.10" if field in ("item", "purpose", "spec") else None
    assert report["estimated_total_cny"] == expected_total


def test_review_is_repeatable_and_does_not_mutate_application_or_policy():
    application = equipment(item="  显示器  ")
    original = deepcopy(application)
    first = review_equipment(application)
    assert application == original
    assert first["materials"]["item"] == "显示器"
    assert first == review_equipment(application)
    first["clauses"]["EQ-1"] = "changed by caller"
    assert review_equipment(application)["clauses"]["EQ-1"] != "changed by caller"


@pytest.mark.parametrize("amount", ["0.01", 12, Decimal("12.30")])
def test_decimal_amounts_keep_exact_cents(amount):
    report = review_equipment(equipment(amount=amount, quantity=3))
    assert report["status"] == "ready_for_review"
    assert Decimal(report["estimated_total_cny"]) == Decimal(str(amount)) * 3
