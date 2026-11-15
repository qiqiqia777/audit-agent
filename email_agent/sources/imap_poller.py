"""IMAP 轮询事件源（R1 / R9 事件级幂等）。

- UID 增量同步：游标 last_uid 持久化于 <data_dir>/imap_state.json，重启续传（K2：不丢游标）
- 去重窗口：全新启动（无游标）只捡起启动前 1 分钟内的存量邮件，更旧的记为基线不产生事件（R1.2）
- Message-ID 去重：同 Message-ID 不重复入队（R9.1）
- 失败退避：连续失败告警并放慢轮询，游标不动（K2）

imap-tools 适配通过 ImapToolsClient（短连接）隔离，单测用假客户端注入 client_factory。
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from email_agent.config import ImapConfig
from email_agent.events import Event, EventType
from email_agent.sources.base import ThreadedEventSource

logger = logging.getLogger(__name__)

SEEN_IDS_CAP = 5000
MAX_BACKOFF = 10
# 单轮轮询的总期限（秒）：socket 超时管不住服务器涓流响应（每个 read 都没超时、
# 整体却悬挂），所以轮询在工作线程里跑，超过期限整轮遗弃（真实环境踩过）。
POLL_DEADLINE_SECONDS = 90.0
# 被遗弃轮次的僵尸线程宽限期（秒）：宽限内它完成则**立即补拉**（覆盖悬挂期间的
# 新邮件）；宽限外继续等待、绝不并发第二轮（两个 poll_once 会竞态写游标、重复
# 发事件）。僵尸实测最长 ~3.5 分钟（服务端最终断开）。
ZOMBIE_GRACE_SECONDS = 180.0


def _as_naive(dt: datetime | None) -> datetime | None:
    """统一为本地 naive datetime，避免 aware/naive 比较报错。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _message_id(raw_msg: Any) -> str:
    """提取 Message-ID。

    注意：imap-tools 1.x 的 MailMessage.headers 是 LazyHeaders——有 .get 但不是
    dict 实例，禁止用 isinstance(headers, dict) 判断（真实环境踩过坑）。
    """
    headers = getattr(raw_msg, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        values = headers.get("message-id") or ()
        if values:
            return str(values[0]).strip()
    msg = getattr(raw_msg, "msg", None)
    if msg is not None and hasattr(msg, "get"):
        return str(msg.get("Message-ID") or "").strip()
    if hasattr(raw_msg, "get"):
        return str(raw_msg.get("Message-ID") or "").strip()
    return ""


def _since(date):
    from imap_tools import AND

    # imap-tools >=1.15：IMAP SINCE 语义对应 date_gte（INTERNALDATE >= date）
    return AND(date_gte=date)


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and "last_uid" in data:
        return data
    return None


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class ImapToolsClient:
    """imap-tools 适配器：每次轮询建立短连接（对掉线健壮、实现简单）。

    timeout 必须显式给——socket 默认无超时，QQ 侧限流/半开连接会让登录永久挂起，
    表现为轮询线程静默失联（真实环境踩过）。
    """

    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX", timeout: float = 30.0) -> None:
        self._host, self._user, self._password, self._folder = host, user, password, folder
        self._timeout = timeout
        self._box = None

    def __enter__(self) -> "ImapToolsClient":
        from imap_tools import MailBox

        self._box = MailBox(self._host, timeout=self._timeout).login(
            self._user, self._password, initial_folder=self._folder
        )
        return self

    def __exit__(self, *exc_info) -> bool:
        try:
            self._box.logout()
        except Exception:  # noqa: BLE001 —— logout 失败不影响结果
            logger.debug("IMAP logout 异常已忽略", exc_info=True)
        self._box = None
        return False

    def fetch(self, criteria, *, mark_seen: bool = False) -> list:
        return list(self._box.fetch(criteria, mark_seen=mark_seen))

    def uids(self) -> list[str]:
        return list(self._box.uids())


class ImapPoller(ThreadedEventSource):
    def __init__(
        self,
        event_queue: "queue.Queue[Event]",
        imap: ImapConfig,
        data_dir: Path,
        *,
        poll_interval: float = 60.0,
        client_factory: Callable[[], Any] | None = None,
        startup_time: datetime | None = None,
        fresh_window_minutes: float = 1.0,
    ) -> None:
        super().__init__(name="imap", event_queue=event_queue)
        self._imap = imap
        self._state_path = data_dir / "imap_state.json"
        self.poll_interval = poll_interval
        self._startup_time = _as_naive(startup_time) or datetime.now()
        self._fresh_window_minutes = fresh_window_minutes
        if client_factory is None:
            def client_factory():
                return ImapToolsClient(imap.host, imap.user, imap.password, imap.folder, timeout=30.0)
        self._client_factory = client_factory
        self._consecutive_failures = 0
        self._backoff = 1

    def run(self) -> None:
        worker: threading.Thread | None = None
        done = threading.Event()
        grace_until = 0.0
        poll_round = 0
        while not self.stopping:
            if worker is not None and worker.is_alive():
                # 上一轮被遗弃且僵尸仍在：等它结束（期间新邮件不可见，已知权衡），
                # 它一结束立即补拉，把失明窗口压到悬挂时长本身
                remaining = grace_until - time.monotonic()
                if remaining > 0:
                    logger.error(
                        "第 %d 轮 IMAP 轮询悬挂中（限流/网络），期间新邮件不可见；其完成将立即补拉（宽限剩余 %.0fs）",
                        poll_round, remaining,
                    )
                    outcome = self._wait_any(done, remaining)
                    if outcome == "stop":
                        break
                    if outcome == "done":
                        logger.warning("被遗弃的第 %d 轮已完成，立即补拉覆盖悬挂期间的新邮件", poll_round)
                        worker = None
                    else:
                        logger.error(
                            "第 %d 轮悬挂超过 %.0fs 宽限仍未结束，继续等待（不并发，防游标竞态）；长期不恢复建议重启进程",
                            poll_round, ZOMBIE_GRACE_SECONDS,
                        )
                        continue
                else:
                    worker = None
            poll_round += 1
            done = threading.Event()
            worker = threading.Thread(
                target=self._poll_worker, args=(poll_round, done), name=f"imap-poll-{poll_round}", daemon=True
            )
            worker.start()
            worker.join(timeout=POLL_DEADLINE_SECONDS)
            if worker.is_alive():
                grace_until = time.monotonic() + ZOMBIE_GRACE_SECONDS
                logger.error(
                    "IMAP 第 %d 轮轮询超过 %.0fs 未完成，已遗弃该轮；其完成将立即触发补拉",
                    poll_round, POLL_DEADLINE_SECONDS,
                )
                continue
            if self._stop_event.wait(self.poll_interval * self._backoff):
                break

    def _poll_worker(self, poll_round: int, done: threading.Event) -> None:
        try:
            emitted = self.poll_once()
            self._consecutive_failures = 0
            self._backoff = 1
            if emitted == 0:
                logger.info("IMAP 第 %d 次轮询完成，无新邮件", poll_round)
        except Exception as exc:  # noqa: BLE001 —— K2：告警 + 退避，游标不动
            self._consecutive_failures += 1
            if self._consecutive_failures >= 5:
                logger.error(
                    "IMAP 轮询连续失败 %d 次，已降速至 %dx 间隔: %s",
                    self._consecutive_failures, self._backoff, exc,
                )
            else:
                logger.warning("IMAP 轮询失败（第 %d 次）: %s", self._consecutive_failures, exc)
            self._backoff = min(self._backoff * 2, MAX_BACKOFF)
        finally:
            done.set()

    def _wait_any(self, done: threading.Event, timeout: float) -> str:
        """等待僵尸完成（done）/ stop / 超时，返回 'done' | 'stop' | 'timeout'。"""
        deadline = time.monotonic() + timeout
        while not self._stop_event.is_set():
            if done.is_set():
                return "done"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout"
            done.wait(timeout=min(0.5, remaining))
        return "stop"

    def poll_once(self) -> int:
        """执行一轮拉取，返回本轮产生的事件数。测试可直接同步调用。"""
        state = _load_state(self._state_path)
        fresh = state is None
        window_start = self._startup_time - timedelta(minutes=self._fresh_window_minutes)
        if fresh:
            since_date = window_start.date() - timedelta(days=1)
        else:
            since_date = datetime.strptime(state["since_date"], "%Y-%m-%d").date() - timedelta(days=1)

        emitted = 0
        with self._client_factory() as client:
            if fresh:
                all_uids = [int(u) for u in client.uids()]
                last_uid = max(all_uids) if all_uids else 0
                seen: dict[str, None] = {}
                # R1.2：全新启动只捡启动前 1 分钟内的存量邮件，更旧的交给基线游标
                candidates = [
                    m
                    for m in client.fetch(_since(since_date), mark_seen=False)
                    if (_as_naive(getattr(m, "date", None)) or datetime.min) >= window_start
                ]
            else:
                last_uid = int(state["last_uid"])
                seen = dict.fromkeys(state.get("seen_ids", []))
                candidates = [
                    m for m in client.fetch(_since(since_date), mark_seen=False) if int(m.uid) > last_uid
                ]

            candidates.sort(key=lambda m: (_as_naive(getattr(m, "date", None)) or datetime.min, int(m.uid)))

            for m in candidates:
                mid = _message_id(m)
                if mid and mid in seen:
                    logger.info("跳过已见 Message-ID: uid=%s", m.uid)
                    last_uid = max(last_uid, int(m.uid))
                    continue
                self._emit_email(m, mid)
                emitted += 1
                if mid:
                    seen[mid] = None
                last_uid = max(last_uid, int(m.uid))

        _save_state(
            self._state_path,
            {
                "last_uid": last_uid,
                "seen_ids": list(seen)[-SEEN_IDS_CAP:],
                "since_date": datetime.now().date().isoformat(),
            },
        )
        if emitted:
            logger.info("IMAP 轮询产生 %d 个邮件事件（游标推进到 uid=%s）", emitted, last_uid)
        return emitted

    def _emit_email(self, m: Any, mid: str) -> None:
        subject = str(getattr(m, "subject", "") or "")
        body = str(getattr(m, "text", "") or "")
        from_ = str(getattr(m, "from_", "") or "")
        to = getattr(m, "to", "")
        to = ", ".join(to) if isinstance(to, (list, tuple)) else str(to or "")
        date = _as_naive(getattr(m, "date", None))
        headers = getattr(m, "headers", {}) or {}
        def header(name):
            values = headers.get(name) or ()
            return values if isinstance(values, str) else " ".join(map(str, values))
        self.emit(
            Event(
                event_type=EventType.EMAIL_INBOUND,
                content=subject,
                metadata={
                    "message_id": mid,
                    "in_reply_to": header("in-reply-to"),
                    "references": header("references"),
                    "audit_message_id": header("x-audit-message-id"),
                    "uid": str(getattr(m, "uid", "")),
                    "from": from_,
                    "to": to,
                    "subject": subject,
                    "email_thread": body,
                    "date": date.isoformat(timespec="seconds") if date else "",
                },
            )
        )
