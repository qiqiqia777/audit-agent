"""T1.3：IMAP 轮询器——去重窗口、UID 游标、Message-ID 去重、排序、退避（R1/R9/K2）。

用假邮箱客户端注入 client_factory，不触网；真实邮箱验证待 .env 凭据（已知未验证项）。
"""

import logging
import queue
import threading
from datetime import datetime, timedelta
from pathlib import Path


from email_agent.config import ImapConfig
from email_agent.events import EventType
from email_agent.sources.imap_poller import ImapPoller, _load_state, _save_state

IMAP = ImapConfig(host="imap.test", port=993, user="me@test", password="pw", folder="INBOX")


class FakeHeaders:
    """模拟 imap_tools 的 LazyHeaders：有 .get 但不是 dict（回归 R9.1 真实形态）。"""

    def __init__(self, mapping: dict):
        self._mapping = mapping

    def get(self, key, default=None):
        return self._mapping.get(key, default)


class FakeMessage:
    """模拟 imap_tools.MailMessage 的鸭子类型（headers 非 dict、to 为元组）。"""

    def __init__(self, uid: str, subject: str, date: datetime, message_id: str = "", text: str = ""):
        self.uid = uid
        self.subject = subject
        self.date = date
        self.text = text
        self.from_ = "sender@example.com"
        self.to = ("me@example.com",)
        self.headers = FakeHeaders({"message-id": (message_id,)}) if message_id else FakeHeaders({})


class FakeClient:
    def __init__(self, messages: list[FakeMessage]):
        self.messages = messages
        self.fetch_mark_seen: list[bool] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetch(self, criteria, *, mark_seen: bool = False):
        self.fetch_mark_seen.append(mark_seen)
        return list(self.messages)

    def uids(self):
        return [m.uid for m in self.messages]


class FlakyClient(FakeClient):
    def __enter__(self):
        raise ConnectionError("IMAP 服务器失联")


def make_poller(tmp_path: Path, messages, startup_time=None, factory=None):
    q = queue.Queue()
    poller = ImapPoller(
        q,
        IMAP,
        tmp_path,
        poll_interval=60.0,
        client_factory=factory or (lambda: FakeClient(messages)),
        startup_time=startup_time or datetime(2026, 9, 14, 12, 0, 0),
    )
    return poller, q


def drain(q: queue.Queue) -> list:
    events = []
    while True:
        try:
            events.append(q.get_nowait())
        except queue.Empty:
            return events


def test_fresh_start_window_skips_old_mail(tmp_path):
    startup = datetime(2026, 9, 14, 12, 0, 0)
    old = FakeMessage("1", "很旧的邮件", datetime(2026, 9, 1, 9, 0, 0))
    recent = FakeMessage("2", "刚好在窗口内", startup - timedelta(seconds=30))
    poller, q = make_poller(tmp_path, [old, recent], startup_time=startup)

    emitted = poller.poll_once()

    assert emitted == 1  # R1.2：窗口外的旧邮件不产生事件
    events = drain(q)
    assert [e.content for e in events] == ["刚好在窗口内"]
    assert events[0].event_type is EventType.EMAIL_INBOUND
    assert events[0].metadata["uid"] == "2"
    # 游标推进到当前最大 uid，旧邮件从此不再被考虑
    assert _load_state(poller._state_path)["last_uid"] == 2


def test_fresh_window_minutes_extensible(tmp_path):
    startup = datetime(2026, 9, 14, 12, 0, 0)
    three_min_ago = FakeMessage("1", "默认窗口外", startup - timedelta(minutes=3))
    poller, q = make_poller(tmp_path, [three_min_ago], startup_time=startup)
    poller._fresh_window_minutes = 5  # 手动测试场景：回看窗口调大

    assert poller.poll_once() == 1  # 窗口调大后该邮件被捡起
    assert [e.content for e in drain(q)] == ["默认窗口外"]


def test_incremental_poll_picks_new_uid_only(tmp_path):
    startup = datetime.now()
    messages = [FakeMessage("1", "启动前已存在", startup - timedelta(seconds=10), message_id="<m1>")]
    poller, q = make_poller(tmp_path, messages, startup_time=startup)
    poller.poll_once()
    assert drain(q)  # 窗口内的启动前邮件被捡起

    poller._client_factory = lambda: FakeClient(messages)  # 无新邮件
    assert poller.poll_once() == 0  # R9.1：重复轮询不重复处理
    assert not drain(q)

    messages.append(FakeMessage("2", "新邮件", startup + timedelta(seconds=30), message_id="<m2>"))
    assert poller.poll_once() == 1
    assert [e.metadata["message_id"] for e in drain(q)] == ["<m2>"]


def test_message_id_dedup_on_redelivery(tmp_path):
    startup = datetime.now()
    messages = []
    poller, q = make_poller(tmp_path, messages, startup_time=startup)
    poller.poll_once()

    messages.append(FakeMessage("5", "第一封", startup, message_id="<dup>"))
    assert poller.poll_once() == 1
    messages.append(FakeMessage("6", "同 Message-ID 重投", startup, message_id="<dup>"))
    assert poller.poll_once() == 0  # R9.1：同 Message-ID 不重复入队
    assert len(drain(q)) == 1


def test_cursor_persisted_across_restart(tmp_path):
    startup = datetime.now()
    messages = [FakeMessage("7", "已有邮件", startup, message_id="<a>")]
    poller_a, q_a = make_poller(tmp_path, messages, startup_time=startup)
    poller_a.poll_once()
    assert len(drain(q_a)) == 1

    # 重启：新实例共享同一状态文件
    poller_b, q_b = make_poller(tmp_path, messages, startup_time=datetime.now())
    assert poller_b.poll_once() == 0
    assert not drain(q_b)


def test_sorted_by_date_then_uid(tmp_path):
    startup = datetime(2026, 9, 14, 12, 0, 0)
    # 预置游标=1，走增量分支（绕开窗口过滤，专测排序）
    _save_state(tmp_path / "imap_state.json", {"last_uid": 1, "seen_ids": [], "since_date": "2026-09-14"})
    later = FakeMessage("2", "晚的", datetime(2026, 9, 14, 12, 5, 0), message_id="<b>")
    earlier = FakeMessage("3", "早的", datetime(2026, 9, 14, 11, 0, 0), message_id="<c>")
    poller, q = make_poller(tmp_path, [later, earlier], startup_time=startup)
    poller.poll_once()
    assert [e.content for e in drain(q)] == ["早的", "晚的"]  # FIFO：按 (date, uid) 排序


def test_fetch_never_marks_seen(tmp_path):
    startup = datetime.now()
    client = FakeClient([])
    poller, _ = make_poller(tmp_path, [], startup_time=startup, factory=lambda: client)
    poller.poll_once()
    assert client.fetch_mark_seen and all(m is False for m in client.fetch_mark_seen)


def test_state_written_atomically_and_readable(tmp_path):
    poller, _ = make_poller(tmp_path, [], startup_time=datetime.now())
    poller.poll_once()
    state = _load_state(poller._state_path)
    assert state is not None and "last_uid" in state
    assert not list(tmp_path.glob("*.tmp"))  # 原子替换后无临时文件残留


def test_run_survives_consecutive_failures(tmp_path, caplog):
    poller, _ = make_poller(
        tmp_path, [], startup_time=datetime.now(), factory=lambda: FlakyClient([])
    )
    poller.poll_interval = 0.05
    worker = threading.Thread(target=poller.run, daemon=True)
    with caplog.at_level(logging.WARNING, logger="email_agent.sources.imap_poller"):
        worker.start()
        threading.Event().wait(0.4)
        poller.stop()
        worker.join(timeout=2)
    assert not worker.is_alive()  # R3.2/K2：连续失败不崩溃，退避后继续
    assert any("IMAP 轮询失败" in r.message for r in caplog.records)
    assert _load_state(poller._state_path) is None  # 失败时游标不被错误写入


def test_watchdog_abandons_hung_poll(tmp_path, monkeypatch, caplog):
    """涓流悬挂回归：单轮超过总期限被遗弃并进入宽限等待，循环存活。"""
    import email_agent.sources.imap_poller as mod

    class HangingClient(FakeClient):
        def fetch(self, criteria, *, mark_seen: bool = False):
            threading.Event().wait(5)  # 模拟服务器涓流悬挂
            return []

    poller, _ = make_poller(tmp_path, [], startup_time=datetime.now(),
                            factory=lambda: HangingClient([]))
    poller.poll_interval = 0.05
    monkeypatch.setattr(mod, "POLL_DEADLINE_SECONDS", 0.2)
    worker = threading.Thread(target=poller.run, daemon=True)
    with caplog.at_level(logging.ERROR, logger="email_agent.sources.imap_poller"):
        worker.start()
        threading.Event().wait(1.0)
        poller.stop()
        worker.join(timeout=2)
    assert not worker.is_alive()
    assert any("已遗弃该轮" in r.message for r in caplog.records)


def test_zombie_done_triggers_immediate_repoll(tmp_path, monkeypatch):
    """悬挂轮被遗弃后，僵尸一完成就立即补拉（不等剩余轮询间隔）——失明窗口回归护栏。"""
    import email_agent.sources.imap_poller as mod
    import time as _time

    calls = {"n": 0}

    class RecoverClient(FakeClient):
        def fetch(self, criteria, *, mark_seen: bool = False):
            calls["n"] += 1
            if calls["n"] == 1:
                threading.Event().wait(0.6)  # 第 1 轮悬挂，超过 0.2s 期限
            return list(self.messages)

    _save_state(tmp_path / "imap_state.json", {"last_uid": 1, "seen_ids": [], "since_date": "2026-09-14"})
    pending = FakeMessage("2", "悬挂期间到达", datetime.now(), message_id="<late>")
    poller, q = make_poller(tmp_path, [pending], startup_time=datetime.now(),
                            factory=lambda: RecoverClient([pending]))
    poller.poll_interval = 5.0  # 若修复失效，补拉要等满 5s 间隔，测试窗口内必然收不到
    monkeypatch.setattr(mod, "POLL_DEADLINE_SECONDS", 0.2)
    monkeypatch.setattr(mod, "ZOMBIE_GRACE_SECONDS", 5.0)

    worker = threading.Thread(target=poller.run, daemon=True)
    worker.start()
    events = []
    deadline = _time.monotonic() + 2.5
    while _time.monotonic() < deadline and not events:
        try:
            events.append(q.get(timeout=0.1))
        except queue.Empty:
            pass
    poller.stop()
    worker.join(timeout=3)
    assert not worker.is_alive()  # stop 可中断宽限等待，干净退出
    assert [e.content for e in events] == ["悬挂期间到达"]  # 2.5s 内收到 → 立即补拉生效


def test_message_id_extraction_variants():
    from email.message import Message
    from types import MappingProxyType
    from email_agent.sources.imap_poller import _message_id

    m = FakeMessage("1", "s", datetime.now(), message_id="<x@y>")
    assert _message_id(m) == "<x@y>"
    # 鸭子类型 message 对象（非 Message 实例但带 .get("Message-ID") 返回字符串）走兜底分支
    proxy = MappingProxyType({"Message-ID": "<proxy@x>"})
    assert _message_id(proxy) == "<proxy@x>"
    plain = Message()  # 无 headers 属性的旧式对象走 .get 兜底
    assert _message_id(plain) == ""
    assert _message_id(object()) == ""


def test_poller_matches_protocol(tmp_path):
    from email_agent.sources.base import EventSource

    poller, _ = make_poller(tmp_path, [], startup_time=datetime.now())
    assert isinstance(poller, EventSource)
