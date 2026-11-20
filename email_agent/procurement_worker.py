"""Single local review worker; model calls never hold a SQLite write transaction."""

import argparse
import os
import time
from contextlib import closing, contextmanager

from email_agent.config import AppConfig
from email_agent.procurement import ProcurementStore
from minihermes.config import Settings
from minihermes.loop.agent import ToolArgumentsExhausted
from minihermes.loop.models import get_client
from minihermes.ops.procurement_review import review_request


@contextmanager
def worker_lock(path):
    with path.open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def work_once(store, client, model, max_iterations=6):
    work = store.claim_review()
    if work is None:
        return False
    if work.get("skip"):
        return True
    try:
        result = review_request(client, model, work["snapshot"], max_iterations=max_iterations)
    except ToolArgumentsExhausted as exc:
        store.finish_review(work["job"], result=exc.diagnostics, error=exc.failure_class)
    except Exception as exc:
        # Persist an actionable category, never provider error bodies or credentials.
        store.finish_review(work["job"], error=type(exc).__name__)
    else:
        store.finish_review(work["job"], result)
    return True


def main():
    parser = argparse.ArgumentParser(description="MiniHermes 采购材料审查")
    parser.add_argument("--env-file")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--glm-compat", action="store_true", help="使用邮箱工程的 GLM 配置")
    parser.add_argument("--retry-failed", action="store_true", help="配置修复后重试失败任务")
    args = parser.parse_args()
    cfg = AppConfig.from_env(args.env_file)
    directory = cfg.data_dir / "procurement"
    directory.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    if args.glm_compat:
        settings = Settings(
            provider="openai",
            api_key=os.getenv("GLM_API_KEY", ""),
            base_url=os.getenv("GLM_BASE_URL"),
            model=os.getenv("GLM_MODEL", ""),
        )
        if not settings.api_key or not settings.base_url or not settings.model:
            parser.error("请填写 GLM_API_KEY、GLM_BASE_URL 和 GLM_MODEL")
    client = get_client(settings)
    store = ProcurementStore(directory / "applications.sqlite", model_review=True)
    with worker_lock(directory / "review-worker.lock"):
        with closing(store.connect()) as db, db:
            db.execute("UPDATE review_jobs SET state='pending' WHERE state='running'")
            if args.retry_failed:
                db.execute("UPDATE review_jobs SET state='pending',error=NULL WHERE state='failed'")
        while True:
            processed = work_once(
                store, client, settings.model, max_iterations=settings.max_iterations
            )
            if args.once:
                return
            if not processed:
                time.sleep(1)


if __name__ == "__main__":
    main()
