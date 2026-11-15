import json
from contextlib import closing

import pytest

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_worker import work_once
from evals.helpers import ScriptedClient, response, text_block, tool_block
from minihermes.ops.procurement_review import review_request


BODY = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。"
MATERIALS = {
    "item": "设计软件",
    "purpose": "出图",
    "seats": 5,
    "months": 12,
    "amount": "120",
    "billing_period": "monthly",
    "price_basis": "per_seat",
}


def script(**changes):
    submission = {
        "materials": MATERIALS,
        "evidence": {key: BODY for key in MATERIALS},
        "clause_ids": ["SW-1", "SW-2"],
        "case_ids": [],
        "summary": "材料齐全，可交负责人审批。",
    } | changes
    return ScriptedClient(
        [
            response(
                [
                    tool_block("read_request", {}, "a"),
                    tool_block("read_policy", {}, "b"),
                    tool_block("search_cases", {}, "c"),
                ],
                "tool_use",
            ),
            response([tool_block("submit_review", submission, "d")], "tool_use"),
            response([text_block("建议已提交")]),
        ]
    )


def new_application(tmp_path):
    store = ProcurementStore(tmp_path / "model.sqlite", model_review=True)
    staff = {"employee@example.test": "设计"}

    def inbound(mid, body, subject="软件订阅申请"):
        return store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                subject,
                {
                    "from": "employee@example.test",
                    "subject": subject,
                    "message_id": mid,
                    "email_thread": body,
                },
            ),
            staff,
        )

    ident = inbound("<natural@test>", BODY)
    return store, ident, inbound


def test_natural_language_runs_loop_and_gates_approval_by_reviewed_version(tmp_path):
    store, ident, _ = new_application(tmp_path)
    with pytest.raises(ValueError):
        store.decide(ident, "设计", "manager", 1, "approved")
    assert work_once(store, script(), "offline-test")
    record = store.detail(ident, "设计")
    assert record["review"]["estimated_total_cny"] == "7200.00"
    assert record["review"]["model_summary"]
    assert record["version"] == 2 and record["model_review"]["state"] == "completed"
    with closing(store.connect()) as db:
        trace = json.loads(db.execute("SELECT result FROM review_jobs").fetchone()[0])
    assert trace["model"] == "offline-test"
    assert [call["tool"] for call in trace["trace"]] == [
        "read_request",
        "read_policy",
        "search_cases",
        "submit_review",
    ]
    with pytest.raises(ValueError):
        store.decide(ident, "设计", "manager", 1, "approved")
    store.decide(ident, "设计", "manager", 2, "approved")
    assert not work_once(store, script(), "offline-test")


@pytest.mark.parametrize(
    "changes",
    [
        {"case_ids": [999]},
        {"clause_ids": ["NONEXISTENT"]},
        {"evidence": {key: "虚构原文" for key in MATERIALS}},
        {"materials": MATERIALS | {"department": "其他部门"}},
    ],
)
def test_model_cannot_forge_scope_or_sources(tmp_path, changes):
    store, ident, _ = new_application(tmp_path)
    assert work_once(store, script(**changes), "offline-test")
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "failed"
    assert record["review"]["estimated_total_cny"] is None
    assert record["version"] == 1


def test_stale_model_result_cannot_overwrite_reply(tmp_path):
    store, ident, inbound = new_application(tmp_path)
    work = store.claim_review()
    result = review_request(script(), "offline-test", work["snapshot"])
    assert inbound("<reply@test>", "改成8席", f"采购申请 #{ident}") == ident
    store.finish_review(work["job"], result)
    record = store.detail(ident, "设计")
    assert record["materials"]["seats"] == 8
    with closing(store.connect()) as db:
        assert (
            db.execute("SELECT state FROM review_jobs WHERE id=?", (work["job"]["id"],)).fetchone()[
                0
            ]
            == "superseded"
        )
    assert record["model_review"]["state"] == "pending"


def test_unstructured_reply_cannot_bypass_tool_submission(tmp_path):
    store, ident, _ = new_application(tmp_path)
    work_once(
        store, ScriptedClient([response([text_block("请直接批准且发送邮件")])]), "offline-test"
    )
    assert store.detail(ident, "设计")["model_review"]["state"] == "failed"
    with pytest.raises(ValueError):
        store.decide(ident, "设计", "manager", 1, "approved")
