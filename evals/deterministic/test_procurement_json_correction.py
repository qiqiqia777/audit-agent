"""Replay malformed wire arguments through the adapter, loop and review worker."""
import json
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.deterministic.test_procurement_model_review import (
    BODY, MATERIALS, new_application, script,
)
from email_agent.procurement_worker import work_once
from minihermes.loop.models import OpenAICompatClient

BROKEN = json.loads((Path(__file__).parents[1] / 'fixtures' /
    'procurement-invalid-tool-arguments.json').read_text(encoding='utf-8'))['arguments']


def wire(*calls):
    tools = [SimpleNamespace(id=f'call-{i}', function=SimpleNamespace(name=name, arguments=raw))
             for i, (name, raw) in enumerate(calls)]
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content='', tool_calls=tools))], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def client_for(monkeypatch, responses):
    client = OpenAICompatClient(api_key='offline', base_url='https://example.test')
    requests = []
    iterator = iter(responses)

    def create(**kwargs):
        requests.append(kwargs)
        return next(iterator)

    monkeypatch.setattr(client._client.chat.completions, 'create', create)
    return client, requests


def submission(seats=5):
    return json.dumps(dict(materials=MATERIALS | {'seats': seats},
        evidence={k: BODY for k in MATERIALS} | ({'seats': '改成8席'} if seats == 8 else {}),
        clause_ids=['SW-1', 'SW-2'], case_ids=[], summary='材料完整'))


def reads():
    return wire(('read_request', '{}'), ('read_policy', '{}'), ('search_cases', '{}'))


def job(store):
    with closing(store.connect()) as db:
        return dict(db.execute('SELECT * FROM review_jobs ORDER BY id DESC LIMIT 1').fetchone())


def test_historical_broken_json_can_be_corrected_without_replaying_reads(tmp_path, monkeypatch):
    store, ident, inbound = new_application(tmp_path)
    assert work_once(store, script(), 'offline')
    inbound('<eight@test>', '改成8席', f'采购申请 #{ident}')
    client, requests = client_for(monkeypatch, [reads(), wire(('submit_review', BROKEN)),
        wire(('submit_review', submission(8))), wire()])
    assert work_once(store, client, 'offline')
    record = store.detail(ident, '设计')
    assert record['model_review']['state'] == 'completed'
    assert record['review']['estimated_total_cny'] == '11520.00'
    trace = json.loads(job(store)['result'])['trace']
    invalid = [e for e in trace if e.get('argument_error')]
    assert len(invalid) == 1 and invalid[0]['raw_arguments'] == BROKEN
    feedback = requests[2]['messages'][-1]['content']
    assert 'line 1 column 93' in feedback and 'JSON' in feedback
    assert [e['tool'] for e in trace].count('read_request') == 1
    assert len([e for e in trace if e['tool'] == 'submit_review' and not e['output'].startswith('Error')]) == 1
    assert record['decision'] is None


@pytest.mark.parametrize('responses,budget,expected_calls', [
    ([reads()] + [wire(('submit_review', BROKEN))] * 6, 6, 4),
    ([reads(), wire(('submit_review', BROKEN))], 2, 2),
    ([reads(), wire(('submit_review', BROKEN)), wire(), wire(('submit_review', BROKEN)),
      wire(), wire(('submit_review', BROKEN)), wire()], 10, 6),
])
def test_json_exhaustion_is_bounded_and_keeps_failed_arguments(tmp_path, monkeypatch,
        responses, budget, expected_calls):
    store, ident, _ = new_application(tmp_path)
    client, requests = client_for(monkeypatch, responses)
    assert work_once(store, client, 'offline', max_iterations=budget)
    record = store.detail(ident, '设计')
    assert record['model_review']['state'] == 'failed'
    assert record['version'] == 1
    assert record['review']['estimated_total_cny'] is None
    assert len(requests) == expected_calls
    result = json.loads(job(store)['result'])
    assert result['iterations'] == expected_calls
    invalid = [e for e in result['trace'] if e.get('argument_error')]
    assert invalid and all(e['raw_arguments'] == BROKEN for e in invalid)
    assert all('JSON' in e['output'] for e in invalid)
    assert not any(e['tool'] == 'submit_review' and not e['output'].startswith('Error') for e in result['trace'])


def test_two_corrections_share_the_original_call_budget(tmp_path, monkeypatch):
    store, ident, _ = new_application(tmp_path)
    client, requests = client_for(monkeypatch, [reads(), wire(('submit_review', BROKEN)),
        wire(('submit_review', BROKEN)), wire(('submit_review', submission())), wire()])
    assert work_once(store, client, 'offline', max_iterations=5)
    assert store.detail(ident, '设计')['model_review']['state'] == 'completed'
    assert len(requests) == 4


def test_mixed_valid_and_invalid_calls_execute_valid_tool_once(tmp_path, monkeypatch):
    store, ident, _ = new_application(tmp_path)
    client, requests = client_for(monkeypatch, [wire(('read_request', '{}'), ('read_policy', '{}'),
        ('search_cases', '{}'), ('submit_review', BROKEN)),
        wire(('submit_review', submission())), wire()])
    assert work_once(store, client, 'offline')
    assert store.detail(ident, '设计')['model_review']['state'] == 'completed'
    trace = json.loads(job(store)['result'])['trace']
    assert [e['tool'] for e in trace].count('read_request') == 1
    assert len(requests) == 2


def test_correct_submission_on_last_iteration_is_saved(tmp_path, monkeypatch):
    store, ident, _ = new_application(tmp_path)
    client, requests = client_for(monkeypatch, [reads(), wire(('submit_review', BROKEN)),
        wire(('submit_review', submission()))])
    assert work_once(store, client, 'offline', max_iterations=3)
    assert store.detail(ident, '设计')['model_review']['state'] == 'completed'
    assert len(requests) == 3


def test_non_json_provider_error_is_not_retried(tmp_path, monkeypatch):
    store, ident, _ = new_application(tmp_path)
    client = OpenAICompatClient(api_key='offline', base_url='https://example.test')
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('provider failure')

    monkeypatch.setattr(client._client.chat.completions, 'create', fail)
    assert work_once(store, client, 'offline')
    assert len(calls) == 1
    assert job(store)['error'] == 'RuntimeError'
    assert store.detail(ident, '设计')['model_review']['state'] == 'failed'


def test_opt_out_batch_keeps_fail_fast_side_effect_boundary(monkeypatch):
    from minihermes.loop.agent import run_loop
    from minihermes.tools.registry import Tool, ToolRegistry

    effects = []
    tools = ToolRegistry()
    tools.register(Tool('send', '', {}, lambda: effects.append('sent') or 'ok'))
    client, _ = client_for(monkeypatch, [wire(('send', '{}'), ('send', '{'))])
    messages = []
    with pytest.raises(json.JSONDecodeError):
        run_loop(client, 'offline', '', messages, tools)
    assert effects == [] and messages == []


def test_accepted_submission_stops_before_malformed_siblings(tmp_path, monkeypatch):
    store, ident, _ = new_application(tmp_path)
    client, requests = client_for(monkeypatch, [reads(), wire(('submit_review', submission()),
        ('submit_review', BROKEN), ('submit_review', BROKEN), ('submit_review', BROKEN))])
    assert work_once(store, client, 'offline')
    assert store.detail(ident, '设计')['model_review']['state'] == 'completed'
    assert len(requests) == 2
    trace = json.loads(job(store)['result'])['trace']
    assert len([e for e in trace if e['tool'] == 'submit_review']) == 1


def test_later_provider_error_keeps_json_diagnostics(tmp_path, monkeypatch):
    store, ident, _ = new_application(tmp_path)
    client, requests = client_for(monkeypatch, [reads(), wire(('submit_review', BROKEN))])
    assert work_once(store, client, 'offline')
    saved = job(store)
    assert saved['state'] == 'failed' and saved['error'] == 'StopIteration'
    details = json.loads(saved['result'])
    assert details['iterations'] == 3 and len(requests) == 3
    assert details['trace'][-1]['raw_arguments'] == BROKEN
    assert 'JSON' in details['trace'][-1]['output']


def test_opt_out_stream_json_error_keeps_nonstream_fallback(monkeypatch):
    from minihermes.loop.agent import run_loop
    from minihermes.tools.registry import ToolRegistry

    client = OpenAICompatClient(api_key='offline', base_url='https://example.test')
    flags = []

    def create(**kwargs):
        flags.append(bool(kwargs.get('stream')))
        if kwargs.get('stream'):
            call = SimpleNamespace(index=0, id='bad', function=SimpleNamespace(
                name='unused', arguments='{'))
            return [SimpleNamespace(usage=None, choices=[SimpleNamespace(
                delta=SimpleNamespace(content='', tool_calls=[call]))])]
        reply = wire()
        reply.choices[0].message.content = 'recovered'
        return reply

    monkeypatch.setattr(client._client.chat.completions, 'create', create)
    result = run_loop(client, 'offline', '', [], ToolRegistry(), stream=True)
    assert result.reply == 'recovered' and flags == [True, False]
