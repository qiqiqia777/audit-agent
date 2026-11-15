"""Run a fictional natural-language sample with configured model credentials."""

import argparse
import json
import tempfile
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from email_agent.events import Event, EventType
from email_agent.procurement import ProcurementStore
from email_agent.procurement_worker import work_once
from minihermes.config import Settings
from minihermes.loop.models import get_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--glm-compat", action="store_true", help="复用邮箱工程的 GLM 配置")
    parser.add_argument("--output", type=Path, required=True, help="脱敏验收结果")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    settings = Settings()
    if args.glm_compat:
        values = dotenv_values(args.env_file)
        settings = Settings(
            provider="openai",
            api_key=values.get("GLM_API_KEY") or "",
            base_url=values.get("GLM_BASE_URL"),
            model=values.get("GLM_MODEL") or "",
        )
        if not settings.api_key or not settings.base_url or not settings.model:
            raise SystemExit("GLM 配置不完整")
    client = get_client(settings)
    body = "申请订阅设计软件用于出图，需要5个席位，订阅12个月，每席位每月120元。"
    with tempfile.TemporaryDirectory() as directory:
        store = ProcurementStore(Path(directory) / "test.sqlite", model_review=True)
        ident = store.intake(
            Event(
                EventType.EMAIL_INBOUND,
                "软件订阅申请",
                {
                    "from": "demo@example.test",
                    "subject": "软件订阅申请",
                    "message_id": "<fictional@sample>",
                    "email_thread": body,
                },
            ),
            {"demo@example.test": "演示部门"},
        )
        work_once(store, client, settings.model)
        result = store.detail(ident, "演示部门")
        evidence = {
            "model": settings.model,
            "transport": settings.provider,
            "review_state": result["model_review"]["state"],
            "error_category": result["model_review"]["error"],
            "expected_total": "7200.00",
            "actual_total": result["review"]["estimated_total_cny"],
            "cited_clauses": result["review"].get("cited_clause_ids", []),
            "evidence_fields": sorted(result["review"].get("evidence", {})),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False))
        if evidence["review_state"] != "completed" or evidence["actual_total"] != "7200.00":
            raise SystemExit("真实模型验收未通过，请查脱敏结果")


if __name__ == "__main__":
    main()
