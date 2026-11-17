import json
from copy import deepcopy

import pytest

from evals.helpers import ScriptedClient, response, text_block
from evals.procurement.runner import grade, load_task, main, run_trial, scripted_client


def test_task_runs_worker_and_reports_without_business_side_effects(tmp_path):
    task = load_task()
    result = run_trial(task, tmp_path / "trial", scripted_client(), "offline-script", "offline")
    assert result["passed"]
    assert all(check["passed"] for check in result["checks"])
    assert result["mode"] == "offline"
    assert result["observed"]["review"]["estimated_total_cny"] == "7200.00"
    assert result["observed"]["decision"] is None
    assert result["observed"]["outbound_count"] == 0
    assert result["trace"]
    assert (tmp_path / "trial" / "calls.json").is_file()
    with pytest.raises(FileExistsError):
        run_trial(task, tmp_path / "trial", scripted_client(), "offline-script", "offline")


@pytest.mark.parametrize("value", ["72000", "NaN", None])
def test_grader_rejects_wrong_or_missing_amount(tmp_path, value):
    task = load_task()
    result = run_trial(task, tmp_path / "trial", scripted_client(), "offline-script", "offline")
    observed = deepcopy(result["observed"])
    observed["review"]["estimated_total_cny"] = value
    checks = grade(task, observed)
    assert not next(c for c in checks if c["id"] == "total")["passed"]


def test_grader_rejects_missing_evidence_and_wrong_field(tmp_path):
    task = load_task()
    result = run_trial(task, tmp_path / "trial", scripted_client(), "offline-script", "offline")
    observed = deepcopy(result["observed"])
    observed["materials"]["seats"] = 8
    observed["review"]["evidence"] = {}
    checks = {c["id"]: c for c in grade(task, observed)}
    assert not checks["materials.seats"]["passed"]
    assert not checks["source_evidence"]["passed"]


def test_model_failure_keeps_evidence_and_fails(tmp_path):
    client = ScriptedClient([response([text_block("未提交")])])
    result = run_trial(load_task(), tmp_path / "trial", client, "offline-script", "offline")
    assert not result["passed"]
    assert result["worker_error"]
    assert result["calls"]
    assert (tmp_path / "trial" / "application.sqlite").is_file()


def test_cli_model_error_is_nonzero_and_writes_failure_report(tmp_path, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("fictional infrastructure failure")

    from types import SimpleNamespace
    monkeypatch.setattr("evals.procurement.runner.scripted_client", lambda:
                        SimpleNamespace(messages=SimpleNamespace(create=broken)))
    directory = tmp_path / "failed"
    assert main(["--output", str(directory)]) == 1
    result = json.loads((directory / "results.jsonl").read_text(encoding="utf-8"))
    assert result["worker_error"] == "RuntimeError"
    assert not result["passed"]
    assert (directory / "summary.md").is_file()


def test_cli_writes_reports_and_does_not_overwrite(tmp_path):
    directory = tmp_path / "run"
    assert main(["--output", str(directory)]) == 0
    result = json.loads((directory / "results.jsonl").read_text(encoding="utf-8"))
    assert result["passed"] and result["task_version"] == "1"
    assert "offline" in (directory / "summary.md").read_text(encoding="utf-8")
    assert result["source"]["commit"]
    with pytest.raises(FileExistsError):
        main(["--output", str(directory)])


def test_cli_database_failure_keeps_structured_failure_report(tmp_path, monkeypatch):
    import sqlite3

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("sensitive adapter error body")

    monkeypatch.setattr("evals.procurement.runner.work_once", broken)
    directory = tmp_path / "db-failure"
    assert main(["--output", str(directory)]) == 1
    result = json.loads((directory / "results.jsonl").read_text(encoding="utf-8"))
    assert not result["passed"]
    assert result["harness_error"] == "OperationalError"
    assert (directory / "summary.md").is_file()
    assert "sensitive adapter error body" not in (directory / "results.jsonl").read_text(
        encoding="utf-8"
    )
