"""发送白名单（R7.3）：系统性护栏——LLM 起草的收件人必须命中白名单才可出站。

白名单防的是注意力失误：人工确认可能顺手 accept 错误收件人，白名单是结构性
拦截而非第二次"看一眼"。
"""

from __future__ import annotations

from collections.abc import Iterable


def normalize(addr: str | None) -> str:
    return (addr or "").strip().lower()


def is_allowed(recipient: str, whitelist: Iterable[str], self_addr: str | None = None) -> bool:
    """收件人（大小写不敏感）命中白名单或本人地址才允许发送。"""
    recipient = normalize(recipient)
    if not recipient:
        return False
    allowed = {normalize(a) for a in whitelist if a}
    if self_addr:
        allowed.add(normalize(self_addr))
    return recipient in allowed
