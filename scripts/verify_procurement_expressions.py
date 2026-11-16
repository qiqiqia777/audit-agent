"""Record fictional software quote expressions through the real model worker."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_worker import work_once
from minihermes.config import Settings
from minihermes.loop.models import get_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    values = dotenv_values(args.env_file)
    settings = Settings(
        provider="openai",
        api_key=values.get("GLM_API_KEY") or "",
        base_url=values.get("GLM_BASE_URL"),
        model=values.get("GLM_MODEL") or "",
    )
    if not settings.api_key or not settings.base_url or not settings.model:
        raise SystemExit("GLM 配置不完整")
    args.directory.mkdir(parents=True, exist_ok=False)
    client = get_client(settings)
    results = []
    for name, expression, basis, total in [
        ("all-seats-short", "全部席位每月120元", "all_seats", "1440.00"),
        ("all-seats-total", "全部席位合计每月120元", "all_seats", "1440.00"),
        ("per-seat-variant", "每个席位每个月费用120元", "per_seat", "7200.00"),
    ]:
        body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，" + expression + "。"
        store = ProcurementStore(args.directory / (name + ".sqlite"), model_review=True)
        ident = store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                "软件订阅申请",
                {
                    "from": "fictional@example.test",
                    "subject": "软件订阅申请",
                    "message_id": f"<{name}@fictional.test>",
                    "email_thread": body,
                },
            ),
            {"fictional@example.test": "演示部"},
        )
        calls = []

        def create(**kwargs):
            # This harness sends fictional material only. Keep tool feedback for
            # diagnosis even when work_once deliberately stores only an error class.
            response = client.messages.create(**kwargs)
            calls.append({"messages": kwargs["messages"][:], "response": response.content})
            (args.directory / (name + "-calls.json")).write_text(
                json.dumps(
                    calls,
                    ensure_ascii=False,
                    indent=2,
                    default=lambda value: (
                        value.model_dump() if hasattr(value, "model_dump") else vars(value)
                    ),
                ),
                encoding="utf-8",
            )
            return response

        work_once(store, SimpleNamespace(messages=SimpleNamespace(create=create)), settings.model)
        record = store.detail(ident, "演示部")
        review = record["review"]
        result = {
            "input": body,
            "model": settings.model,
            "state": record["model_review"]["state"],
            "materials": record["materials"],
            "evidence": review.get("evidence", {}),
            "clauses": review.get("cited_clause_ids", []),
            "expected_total": total,
            "actual_total": review["estimated_total_cny"],
        }
        result["passed"] = (
            result["state"] == "completed"
            and result["actual_total"] == total
            and result["materials"].get("price_basis") == basis
            and result["materials"].get("amount") == "120"
        )
        results.append(result)
        (args.directory / "evidence.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(name, result["state"], result["actual_total"], result["passed"], flush=True)
    if not all(result["passed"] for result in results):
        raise SystemExit("真实模型表达验收未通过；保留全部结果，不覆盖失败抽样")


if __name__ == "__main__":
    main()
