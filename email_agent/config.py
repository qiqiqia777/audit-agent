"""运行配置：env 加载与校验。

凭据只进 .env（gitignore）；启动摘要脱敏（docs/02 §5、K5）。
Wave 2/3 将按需补充 SMTP / SEND_WHITELIST / GLM 字段。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class ImapConfig:
    host: str
    port: int
    user: str
    password: str
    folder: str


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    poll_interval_seconds: float
    imap: ImapConfig | None
    smtp: SmtpConfig | None
    send_whitelist: tuple[str, ...]

    @classmethod
    def from_env(cls, env_file: str | None = None) -> AppConfig:
        load_dotenv(env_file)
        data_dir = Path(os.environ.get("DATA_DIR", "./data"))
        poll_interval = float(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
        if poll_interval <= 0:
            raise ValueError(f"POLL_INTERVAL_SECONDS 必须为正数，当前: {poll_interval}")

        imap: ImapConfig | None = None
        host = os.environ.get("IMAP_HOST", "").strip()
        user = os.environ.get("IMAP_USER", "").strip()
        password = os.environ.get("IMAP_PASSWORD", "").strip()
        if host and user and password:
            imap = ImapConfig(
                host=host,
                port=int(os.environ.get("IMAP_PORT", "993")),
                user=user,
                password=password,
                folder=os.environ.get("IMAP_FOLDER", "INBOX").strip() or "INBOX",
            )
        # SMTP：凭据缺省复用 IMAP（QQ/163 授权码、Gmail App Password 同码可用）
        smtp: SmtpConfig | None = None
        smtp_host = os.environ.get("SMTP_HOST", "").strip()
        if smtp_host and imap is not None:
            smtp = SmtpConfig(
                host=smtp_host,
                port=int(os.environ.get("SMTP_PORT", "465")),
                user=os.environ.get("SMTP_USER", "").strip() or imap.user,
                password=os.environ.get("SMTP_PASSWORD", "").strip() or imap.password,
            )

        # 白名单：SEND_WHITELIST 逗号分隔；缺省只允许发给自己（R7.3）
        raw = os.environ.get("SEND_WHITELIST", "").strip()
        whitelist = tuple(a.strip().lower() for a in raw.split(",") if a.strip())
        if not whitelist and imap is not None:
            whitelist = (imap.user.strip().lower(),)

        return cls(data_dir=data_dir, poll_interval_seconds=poll_interval, imap=imap,
                   smtp=smtp, send_whitelist=whitelist)

    @property
    def receipts_dir(self) -> Path:
        return self.data_dir / "receipts"

    @property
    def imap_state_file(self) -> Path:
        return self.data_dir / "imap_state.json"

    def startup_summary(self) -> list[str]:
        """启动摘要（打印到日志，密码等凭据永不出现）。"""
        lines = [
            f"数据目录: {self.data_dir}",
            f"轮询间隔: {self.poll_interval_seconds:g}s",
        ]
        if self.imap is None:
            lines.append("IMAP: 未配置（--source imap 不可用，请检查 .env 的 IMAP_*）")
        else:
            lines.append(
                f"IMAP: {self.imap.host}:{self.imap.port} user={self.imap.user} "
                f"folder={self.imap.folder} 密码=已配置(不显示)"
            )
        if self.smtp is None:
            lines.append("SMTP: 未配置（accept 后无法真实发送）")
        else:
            lines.append(f"SMTP: {self.smtp.host}:{self.smtp.port} user={self.smtp.user} 密码=已配置(不显示)")
        lines.append(f"发送白名单: {', '.join(self.send_whitelist) or '（空——所有发送将被拦截）'}")
        return lines
