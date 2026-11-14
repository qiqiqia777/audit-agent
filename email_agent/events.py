"""Event 模型与事件类型。

借鉴《深入理解 AI Agent》第 4 章 event_types.py；字段口径见 docs/01-requirements.md 第 9 节术语表。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    """事件类型（可扩展；当前 MVP 两种，见 docs/01 R1/R2）。"""

    EMAIL_INBOUND = "email_inbound"
    TIMER_TRIGGER = "timer_trigger"


def _new_event_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Event:
    """事件对象：事件源产生，事件循环消费（docs/03 §3.1）。"""

    event_type: EventType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)
    event_id: str = field(default_factory=_new_event_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        try:
            event_type = EventType(data["event_type"])
        except KeyError as exc:
            raise ValueError(f"事件缺少 event_type 字段: {data!r}") from exc
        except ValueError as exc:
            raise ValueError(f"未知事件类型: {data.get('event_type')!r}") from exc
        return cls(
            event_type=event_type,
            content=str(data.get("content", "")),
            metadata=dict(data.get("metadata") or {}),
            timestamp=str(data.get("timestamp") or _now_iso()),
            event_id=str(data.get("event_id") or _new_event_id()),
        )
