"""Reject invented quote amounts through the public intake/worker boundary."""

import copy

import pytest

from email_agent.procurement_worker import work_once
from evals.deterministic.test_procurement_model_review import MATERIALS, new_application, script
from evals.helpers import ScriptedClient, response, text_block, tool_block


@pytest.mark.parametrize("amount", ["120元", "120元/季度", "1,20", 120, "600"])
def test_quarterly_amount_feedback_allows_source_preserving_correction(tmp_path, amount):
    body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每季度120元。"
    store, ident, _ = new_application(tmp_path, body)
    materials = MATERIALS | {"billing_period": "quarterly"}
    submission = {
        "materials": materials | {"amount": amount},
        "evidence": {key: body for key in materials},
        "clause_ids": ["SW-1", "SW-2"],
        "case_ids": [],
        "summary": "按原文季度报价提交。",
    }
    client = ScriptedClient([
        response([tool_block(name, {}, name) for name in
                  ("read_request", "read_policy", "search_cases")], "tool_use"),
        response([tool_block("submit_review", submission, "bad")], "tool_use"),
        response([tool_block("submit_review", submission | {"materials": materials}, "ok")], "tool_use"),
        response([text_block("已提交")]),
    ])
    requests = []
    create = client.messages.create

    def capture(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        return create(**kwargs)

    client.messages.create = capture
    assert work_once(store, client, "offline-test")
    feedback = requests[2]["messages"][-1]["content"][0]["content"]
    assert "amount" in feedback
    if amount == "600":
        assert "原文" in feedback and "不能先乘" in feedback
    else:
        assert "纯数字字符串" in feedback and '"120"' in feedback
    schema = next(t for t in requests[0]["tools"] if t["name"] == "submit_review")
    description = schema["input_schema"]["properties"]["materials"]["properties"]["amount"]["description"]
    assert "纯数字字符串" in description and '"120"' in description
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    assert record["materials"]["amount"] == "120"
    assert record["review"]["estimated_total_cny"] == "2400.00"
    assert record["review"]["questions"] == []


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
    # A valid submission is terminal; no extra model call is needed to close it.
    assert len(requests) == min(budget, 3)
    assert record["model_review"]["state"] == ("completed" if budget == 4 else "failed")
    assert record["review"]["estimated_total_cny"] == ("7200.00" if budget == 4 else None)


@pytest.mark.parametrize("label", ["报价", "预计费用"])
@pytest.mark.parametrize("quote_form", ["label", "body"])
def test_labelled_amount_without_currency_can_be_verified(tmp_path, label, quote_form):
    body = f"采购对象：设计软件\n业务用途：出图\n席位数：5\n期限（月）：12\n{label}：120\n计费周期：monthly"
    store, ident, _ = new_application(tmp_path, body)
    materials = {k: v for k, v in MATERIALS.items() if k != "price_basis"}
    quote = f"{label}：120" if quote_form == "label" else body
    evidence = {key: body for key in materials} | {"amount": quote}
    assert work_once(store, script(materials=materials, evidence=evidence), "offline-test")
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    assert record["materials"]["amount"] == "120"
    assert record["review"]["estimated_total_cny"] is None
    with pytest.raises(ValueError):
        store.decide(ident, "设计", "manager", record["version"], "approved")


@pytest.mark.parametrize("raw,amount,quote", [
    ("1200", "120", "报价：120"),
    ("120.123", "120.12", "报价：120.12"),
    ("-120", "120", "报价：-120"),
    ("120", "600", "报价：120"),
])
def test_labelled_amount_does_not_accept_partial_or_invented_prices(tmp_path, raw, amount, quote):
    body = f"采购对象：设计软件\n席位数：5\n期限（月）：12\n报价：{raw}"
    store, ident, _ = new_application(tmp_path, body)
    evidence = {key: body for key in MATERIALS} | {"amount": quote}
    assert work_once(store, script(materials=MATERIALS | {"amount": amount}, evidence=evidence), "offline-test")
    assert store.detail(ident, "设计")["model_review"]["state"] == "failed"
