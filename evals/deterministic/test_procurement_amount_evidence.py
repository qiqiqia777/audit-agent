"""Reject invented quote amounts through the public intake/worker boundary."""

import pytest

from email_agent.procurement_worker import work_once
from evals.deterministic.test_procurement_model_review import MATERIALS, new_application, script
from evals.helpers import ScriptedClient, response, text_block, tool_block


@pytest.mark.parametrize(
    "amount,quote",
    [
        ("600", None),
        ("20", None),
        ("1200", None),
        ("20", "20"),
        ("20", "20元"),
        ("5", "5"),
        ("12", "12"),
    ],
)
def test_unconfirmed_amount_must_match_quoted_currency(tmp_path, amount, quote):
    # This expression is deliberately outside the rule parser's confirmed fields.
    body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每个席位每个月费用120元。"
    store, ident, _ = new_application(tmp_path, body)
    version = store.detail(ident, "设计")["version"]
    evidence = {key: body for key in MATERIALS}
    if quote is not None:
        evidence["amount"] = quote
    assert work_once(
        store, script(materials=MATERIALS | {"amount": amount}, evidence=evidence), "offline-test"
    )
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "failed"
    assert record["version"] == version
    assert record["review"]["estimated_total_cny"] is None
    with pytest.raises(ValueError):
        store.decide(ident, "设计", "manager", version, "approved")


@pytest.mark.parametrize("amount,quote", [("120", "120元"), ("120.00", "120元"), ("120", "120")])
def test_matching_amount_keeps_deterministic_total(tmp_path, amount, quote):
    body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每个席位每个月费用120元。"
    store, ident, _ = new_application(tmp_path, body)
    evidence = {key: body for key in MATERIALS} | {"amount": quote}
    assert work_once(
        store, script(materials=MATERIALS | {"amount": amount}, evidence=evidence), "offline-test"
    )
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    assert record["review"]["estimated_total_cny"] == "7200.00"


def test_model_can_correct_rejected_amount_within_the_same_review(tmp_path):
    body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每个席位每个月费用120元。"
    store, ident, _ = new_application(tmp_path, body)
    submission = {
        "materials": MATERIALS | {"amount": "600"},
        "evidence": {key: body for key in MATERIALS},
        "clause_ids": ["SW-1", "SW-2"],
        "case_ids": [],
        "summary": "原文报价",
    }
    corrected = submission | {"materials": MATERIALS}
    client = ScriptedClient(
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
            response([tool_block("submit_review", corrected, "e")], "tool_use"),
            response([text_block("按120元提交")]),
        ]
    )
    assert work_once(store, client, "offline-test")
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    assert record["materials"]["amount"] == "120"
    assert record["review"]["estimated_total_cny"] == "7200.00"


@pytest.mark.parametrize("budget", [2, 4])
@pytest.mark.parametrize("blocks", [[], [text_block("需要具体软件名称，不能审查")]])
def test_missing_tool_submission_gets_feedback_within_original_iteration_budget(
    tmp_path, blocks, budget
):
    store, ident, _ = new_application(tmp_path)
    submission = {
        "materials": MATERIALS,
        "evidence": {
            key: "120元"
            if key == "amount"
            else "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。"
            for key in MATERIALS
        },
        "clause_ids": ["SW-1", "SW-2"],
        "case_ids": [],
        "summary": "已按制度提交",
    }
    client = ScriptedClient(
        [
            response(
                [
                    tool_block("read_request", {}, "a"),
                    tool_block("read_policy", {}, "b"),
                    tool_block("search_cases", {}, "c"),
                ],
                "tool_use",
            ),
            response(blocks),
            response([tool_block("submit_review", submission, "d")], "tool_use"),
            response([text_block("完成")]),
        ]
    )
    requests = []
    create = client.messages.create

    def record_request(**kwargs):
        requests.append(kwargs)
        return create(**kwargs)

    client.messages.create = record_request
    assert work_once(store, client, "offline-test", max_iterations=budget)
    record = store.detail(ident, "设计")
    assert len(requests) == budget
    assert record["model_review"]["state"] == ("completed" if budget == 4 else "failed")
    assert record["review"]["estimated_total_cny"] == ("7200.00" if budget == 4 else None)
