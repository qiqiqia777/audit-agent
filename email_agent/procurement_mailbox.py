"""Purchasing mailbox command. Commit each inbound application before advancing IMAP."""

import argparse
import json
from pathlib import Path

from email_agent.config import AppConfig
from email_agent.procurement import ProcurementStore
from email_agent.sources.imap_poller import ImapPoller


class ProcurementInbox:
    def __init__(self, store, staff):
        self.store = store
        self.staff = staff

    def put(self, event):
        self.store.intake(event, self.staff)


def main(argv=None):
    parser = argparse.ArgumentParser(description="采购邮箱入站服务")
    parser.add_argument(
        "--roster", required=True, type=Path, help="JSON 名册，staff 为员工邮箱到部门的映射"
    )
    parser.add_argument("--env-file")
    parser.add_argument("--once", action="store_true", help="执行一次同步")
    args = parser.parse_args(argv)
    cfg = AppConfig.from_env(args.env_file)
    if cfg.imap is None:
        parser.error("缺少采购邮箱的 IMAP 配置")
    roster = json.loads(args.roster.read_text(encoding="utf-8"))
    staff = {mailbox.strip().casefold(): dept for mailbox, dept in roster["staff"].items()}
    directory = cfg.data_dir / "procurement"
    directory.mkdir(parents=True, exist_ok=True)
    inbox = ProcurementInbox(
        ProcurementStore(directory / "applications.sqlite", model_review=True), staff
    )
    poller = ImapPoller(inbox, cfg.imap, directory, poll_interval=cfg.poll_interval_seconds)
    if args.once:
        poller.poll_once()
    else:
        try:
            poller.run()
        except KeyboardInterrupt:
            poller.stop()


if __name__ == "__main__":
    main()
