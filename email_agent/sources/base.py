"""EventSource 协议与线程事件源基类。

契约：start / stop / emit（docs/01 R1.3）。事件源为守护线程（docs/03 AD7），
借鉴《深入理解 AI Agent》第 4 章 event_loop_demo.py 的 TriggerSource 模式。
"""

from __future__ import annotations

import queue
import threading
from typing import Protocol, runtime_checkable

from email_agent.events import Event


@runtime_checkable
class EventSource(Protocol):
    """事件源契约：实现方可插拔接入事件循环，图逻辑零改动（R1.3）。"""

    name: str

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def emit(self, event: Event) -> None: ...


class ThreadedEventSource(threading.Thread):
    """守护线程事件源基类：子类实现 run()，通过 emit() 把事件投递到共享队列。"""

    def __init__(self, name: str, event_queue: "queue.Queue[Event]") -> None:
        super().__init__(name=f"source-{name}", daemon=True)
        self.name = name
        self._queue = event_queue
        self._stop_event = threading.Event()
        self._thread_started = False

    def start(self) -> None:
        if self._thread_started:
            return
        self._thread_started = True
        super().start()

    def stop(self) -> None:
        self._stop_event.set()

    def emit(self, event: Event) -> None:
        self._queue.put(event)

    @property
    def stopping(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:  # pragma: no cover - 由子类实现
        raise NotImplementedError
