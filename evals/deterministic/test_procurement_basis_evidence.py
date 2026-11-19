"""Quote scope must be supported, not inferred from a billing period."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from email_agent.procurement_worker import work_once
from evals.deterministic.test_procurement_model_review import MATERIALS, new_application, script
from evals.helpers import ScriptedClient, response, text_block, tool_block


FIXTURE = Path(__file__).parents[1] / "fixtures/procurement/ambiguous-basis-first-submission.json"
AMBIGUOUS = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，报价120元/月。"


@pytest.mark.parametrize("body", [
    AMBIGUOUS,
    "申请订阅设计软件用于出图，需要5个席位，订阅12个月，不能按每席位每月120元计算，报价120元/月，覆盖范围待确认。",
])
def test_original_wrong_scope_can_be_omitted_after_feedback_without_losing_known_facts(tmp_path, body):
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))["submission"]
    corrected = original | {
        "materials": {k: v for k, v in original["materials"].items() if k != "price_basis"},
        "evidence": {k: v for k, v in original["evidence"].items() if k != "price_basis"},
        "summary": "请确认报价覆盖单席还是全部五席。",
    }
    client = ScriptedClient([
        response([
            tool_block("read_request", {}, "a"),
            tool_block("read_policy", {}, "b"),
            tool_block("search_cases", {}, "c"),
        ], "tool_use"),
        response([tool_block("submit_review", original, "d")], "tool_use"),
        response([tool_block("submit_review", corrected, "e")], "tool_use"),
        response([text_block("已保存，等待报价范围澄清。")]),
    ])
    requests = []
    create = client.messages.create

    def capture(**kwargs):
        requests.append(deepcopy(kwargs["messages"]))
        return create(**kwargs)

    client.messages.create = capture
    store, ident, _ = new_application(tmp_path, body)
    assert work_once(store, client, "offline-replay")
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    assert record["materials"] == corrected["materials"]
    assert record["review"]["estimated_total_cny"] is None
    assert record["review"]["status"] == "needs_clarification"
    assert [q["field"] for q in record["review"]["questions"]] == ["price_basis"]
    assert record["decision"] is None
    feedback = [b["content"] for batch in requests for msg in batch
                if isinstance(msg.get("content"), list) for b in msg["content"]
                if isinstance(b, dict) and b.get("type") == "tool_result"
                and b.get("tool_use_id") == "d"]
    assert any("price_basis" in text and "省略" in text for text in feedback)


@pytest.mark.parametrize("body,basis,quote", [
    (AMBIGUOUS, "all_seats", "报价120元/月"),
    (AMBIGUOUS, "per_seat", "需要5个席位"),
    ("申请订阅设计软件用于出图，需要5个席位，订阅12个月，全部五席每月共120元。",
     "per_seat", "全部五席每月共120元"),
    ("申请订阅设计软件用于出图，需要5个席位，订阅12个月，每个席位每个月费用120元。",
     "all_seats", "每个席位每个月费用120元"),
    ("申请订阅设计软件用于出图，需要全部5个席位，订阅12个月，报价120元/月。",
     "all_seats", "需要全部5个席位"),
    ("申请订阅设计软件用于出图，需要5个席位，订阅12个月，不是单席价格，报价120元/月。",
     "per_seat", "单席"),
    ("申请订阅设计软件用于出图，需要5个席位，订阅12个月，不能按每席位每月120元计算，报价120元/月，覆盖范围待确认。",
     "per_seat", "每席位每月120元"),
    ("申请订阅设计软件用于出图，需要5个席位，订阅12个月，报价每席位每月120元吗？覆盖范围待确认。",
     "per_seat", "每席位每月120元"),
])
def test_unsupported_scope_cannot_complete_a_review(tmp_path, body, basis, quote):
    store, ident, _ = new_application(tmp_path, body)
    evidence = {key: body for key in MATERIALS} | {"price_basis": quote}
    assert work_once(store, script(materials=MATERIALS | {"price_basis": basis}, evidence=evidence),
                     "offline-test", max_iterations=3)
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "failed"
    assert record["review"]["estimated_total_cny"] is None
    assert record["decision"] is None


@pytest.mark.parametrize("basis,phrase,quote,total", [
    ("per_seat", "每席位每月120元", "每席位", "7200.00"),
    ("per_seat", "每个席位每个月费用120元", "每个席位", "7200.00"),
    ("all_seats", "全部席位合计每月120元", "全部席位", "1440.00"),
    ("all_seats", "全部五席每月共120元", "全部五席", "1440.00"),
    ("per_seat", "报价120元/席/月", "120元/席/月", "7200.00"),
    ("all_seats", "不是每席位每月120元，而是全部五席每月120元",
     "不是每席位每月120元，而是全部五席每月120元", "1440.00"),
    ("per_seat", "每席位每月120元，是否含税待确认", "每席位每月120元，是否含税待确认", "7200.00"),
    ("per_seat", "每席位每月120元，用途说明不明确", "每席位每月120元，用途说明不明确", "7200.00"),
])
def test_explicit_quoted_scope_keeps_total_and_no_questions(tmp_path, basis, phrase, quote, total):
    body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，" + phrase + "。"
    store, ident, _ = new_application(tmp_path, body)
    evidence = {key: body for key in MATERIALS} | {"price_basis": quote}
    assert work_once(store, script(materials=MATERIALS | {"price_basis": basis}, evidence=evidence),
                     "offline-test")
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    assert record["review"]["estimated_total_cny"] == total
    assert record["review"]["questions"] == []


REPLAYS = json.loads(FIXTURE.with_name("ambiguous-basis-submissions.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("replay", REPLAYS, ids=[
    f"trial-{r['trial']}-submission-{r['submission_number']}" for r in REPLAYS
])
def test_every_preserved_ambiguous_submission_is_rejected(tmp_path, replay):
    store, ident, _ = new_application(tmp_path, AMBIGUOUS)
    assert work_once(store, script(**replay["submission"]), "offline-replay", max_iterations=3)
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "failed"
    assert record["review"]["estimated_total_cny"] is None
