"""Saved manager advice and tool receipts follow the backend review result."""

import json
from contextlib import closing

import pytest

from email_agent.procurement_web import create_app
from email_agent.procurement_worker import work_once
from evals.deterministic.test_procurement_model_review import MATERIALS, new_application, script


@pytest.mark.parametrize("months,total,question_fields", [
    (10, None, ["billing_period"]),
    (12, "2400.00", []),
])
def test_manager_advice_and_receipt_use_actual_quarterly_result(
    tmp_path, months, total, question_fields,
):
    body = f"申请订阅设计软件用于出图，需要5个席位，订阅{months}个月，每席位每季度120元。"
    materials = MATERIALS | {"months": months, "billing_period": "quarterly"}
    # Deliberately wrong draft: the backend must not publish its conclusion.
    draft = "材料齐全，可交负责人审批。" if question_fields else "请补充具体软件名。"
    store, ident, _ = new_application(tmp_path, body)
    assert work_once(store, script(
        materials=materials, evidence={key: body for key in materials}, summary=draft,
    ), "offline-test")
    record = store.detail(ident, "设计")
    review = record["review"]
    assert record["model_review"]["state"] == "completed"
    assert review["estimated_total_cny"] == total
    assert review["status"] == ("needs_clarification" if question_fields else "ready_for_review")
    assert [q["field"] for q in review["questions"]] == question_fields
    assert draft not in review["model_summary"]
    assert review["model_draft_summary"] == draft
    if question_fields:
        assert "待澄清" in review["model_summary"]
        assert "总额待确认" in review["model_summary"]
        for question in review["questions"]:
            assert question["question"] in review["model_summary"]
        with pytest.raises(ValueError):
            store.decide(ident, "设计", "manager", record["version"], "approved")
    else:
        assert "待负责人审批" in review["model_summary"]
        assert "2400.00" in review["model_summary"]
        assert "请补充" not in review["model_summary"]
    with closing(store.connect()) as db:
        result = json.loads(db.execute("SELECT result FROM review_jobs").fetchone()[0])
        receipt = json.loads(next(c["output"] for c in result["trace"] if c["tool"] == "submit_review"))
        assert receipt["status"] == review["status"]
        assert receipt["estimated_total_cny"] == total
        assert receipt["questions"] == review["questions"]
        assert receipt["summary"] == review["model_summary"]
        assert db.execute("SELECT COUNT(*) FROM notification_attempts").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM followup_attempts").fetchone()[0] == 0
    assert record["decision"] is None
    client = create_app(store, {"manager": {"department": "设计"}}, lambda *args: None).test_client()
    with client.session_transaction() as session:
        session["manager"] = "manager"
    page = client.get(f"/requests/{ident}")
    assert page.status_code == 200
    assert review["model_summary"] in page.get_data(as_text=True)
    assert draft not in page.get_data(as_text=True)
