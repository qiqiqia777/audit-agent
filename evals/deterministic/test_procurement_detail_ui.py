import gzip

from email_agent.procurement_worker import work_once
from email_agent.procurement_web import create_app
from evals.deterministic.test_procurement_model_review import new_application, script
from evals.deterministic.test_procurement_followup_recovery import recovery_portal


def ready_page(tmp_path):
    store, ident, _ = new_application(tmp_path)
    assert work_once(store, script(), "offline-test")
    outbox = []
    app = create_app(store, {"lead": {"department": "设计"}}, lambda r, body: outbox.append(body))
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(manager="lead", csrf="ui-test")
    return store, ident, client, outbox


def test_detail_exposes_summary_evidence_and_independent_delivery_state(tmp_path):
    store, ident, client, outbox = ready_page(tmp_path)
    version = store.detail(ident, "设计")["version"]
    store.decide(ident, "设计", "lead", version, "approved")
    attempt = store.detail(ident, "设计")["notification_attempts"][-1]
    store.claim_notification(ident, "设计", "lead", attempt["id"])
    before = store.detail(ident, "设计")
    response = client.get(f"/requests/{ident}")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="request-summary"' in page and "设计软件" in page and "7200.00" in page
    assert "已批准" in page and "结果邮件待核实" in page
    assert 'id="review-evidence"' in page and "SW-1" in page
    assert 'id="original-materials"' in page and 'id="processing-history"' in page
    assert "通知内容版本未单独记录" in page
    assert "lead" in page and "北京时间" in page
    assert store.detail(ident, "设计") == before and outbox == []


def test_detail_keeps_version_bound_confirmation_and_local_assets(tmp_path):
    store, ident, client, outbox = ready_page(tmp_path)
    response = client.get(f"/requests/{ident}")
    page = response.get_data(as_text=True)
    version = store.detail(ident, "设计")["version"]
    assert f'name="version" value="{version}"' in page
    assert 'name="decision" value="approved"' in page and "批准并通知" in page
    assert "tabler-1.7.5.min.css.gz" in page
    assert "https://" not in page and outbox == []
    asset = client.get("/static/procurement/tabler-1.7.5.min.css.gz")
    assert asset.status_code == 200 and asset.headers["Content-Encoding"] == "gzip"
    css = gzip.decompress(asset.data).decode()
    assert "@import" not in css
    assert (
        client.post(
            f"/requests/{ident}", data={"csrf": "wrong", "version": version, "decision": "approved"}
        ).status_code
        == 403
    )
    assert not store.detail(ident, "设计")["decision"] and outbox == []


def test_history_preserves_actual_followup_version_and_records_unknown_metadata(tmp_path):
    store, ident, draft, client, token, calls, _ = recovery_portal(
        tmp_path, "request", OSError("controlled disconnect")
    )
    assert (
        client.post(f"/requests/{ident}", data={"csrf": token, "followup": draft["id"]}).status_code
        == 302
    )
    before = store.detail(ident, "设计")
    page = client.get(f"/requests/{ident}").get_data(as_text=True)
    assert "核实补件结果" in page and "补件请求发送尝试 #" in page
    assert f"版本 {draft['version']}" in page and "manager" in page
    assert "旧数据未保存每次变更的时间与操作者" in page
    assert store.detail(ident, "设计") == before and len(calls) == 1


def test_question_policy_text_stays_visible_when_model_cites_other_clause(tmp_path):
    from evals.deterministic.test_procurement_model_review import MATERIALS

    body = "申请订阅设计软件，需要5个席位，订阅12个月，每席位每月120元。"
    store, ident, _ = new_application(tmp_path, body)
    materials = {k: v for k, v in MATERIALS.items() if k != "purpose"}
    assert work_once(
        store,
        script(materials=materials, evidence={k: body for k in materials}, clause_ids=["SW-2"]),
        "offline-test",
    )
    record = store.detail(ident, "设计")
    assert record["model_review"]["state"] == "completed"
    client = create_app(store, {"lead": {"department": "设计"}}, lambda r, body: None).test_client()
    with client.session_transaction() as session:
        session.update(manager="lead", csrf="ui-test")
    page = client.get(f"/requests/{ident}").get_data(as_text=True)
    assert record["review"]["clauses"]["SW-1"] in page


def test_legacy_migration_does_not_invent_original_send_time_or_actor(tmp_path):
    from email_agent.procurement import ProcurementStore

    store, ident, draft, client, token, calls, _ = recovery_portal(
        tmp_path, "request", OSError("disconnect")
    )
    client.post(f"/requests/{ident}", data={"csrf": token, "followup": draft["id"]})
    with store.connect() as db:
        db.execute("DELETE FROM followup_attempts")
    ProcurementStore(store.path)
    page = client.get(f"/requests/{ident}").get_data(as_text=True)
    assert "旧补件请求记录迁入" in page
    assert "原发送时间与操作者未记录" in page
    assert "migration" not in page
    assert len(calls) == 1


def test_legacy_notification_creation_is_not_labelled_as_original_send(tmp_path):
    from email_agent.procurement import ProcurementStore

    store, ident, client, outbox = ready_page(tmp_path)
    store.decide(ident, "设计", "lead", store.detail(ident, "设计")["version"], "approved")
    with store.connect() as db:
        db.execute("DELETE FROM notification_attempts")
    ProcurementStore(store.path)
    page = client.get(f"/requests/{ident}").get_data(as_text=True)
    assert "结果通知记录创建" in page
    assert "原发送时间与操作者未记录" in page
    assert outbox == []


def test_migrated_wait_preserves_known_original_send_time(tmp_path):
    from email_agent.procurement import ProcurementStore

    store, ident, _, client, _, calls, _ = recovery_portal(tmp_path, "reminder", OSError("unused"))
    with store.connect() as db:
        db.execute("DELETE FROM followup_attempts")
    ProcurementStore(store.path)
    page = client.get(f"/requests/{ident}").get_data(as_text=True)
    assert "原操作者未记录，原发送时间见补件记录" in page
    assert "1970-01-01 08:01:40" in page
    assert not calls
