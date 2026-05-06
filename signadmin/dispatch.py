from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
import fcntl
import hashlib
import sys
import time

from . import config, runtime, store


def _parse_hhmm(value: str) -> dt_time:
    hour, minute = (value or "00:00").split(":", 1)
    return dt_time(int(hour), int(minute))


def _scheduled_at(target: dict, day: datetime) -> datetime:
    start = datetime.combine(day.date(), _parse_hhmm(str(target.get("schedule_start") or "00:20")), day.tzinfo)
    end = datetime.combine(day.date(), _parse_hhmm(str(target.get("schedule_end") or "01:30")), day.tzinfo)
    if end < start:
        end = start
    window_seconds = int((end - start).total_seconds())
    jitter_seconds = max(0, int(target.get("jitter_seconds") or 0))
    if window_seconds > 0:
        span = window_seconds
    else:
        span = jitter_seconds
    if span <= 0:
        return start
    seed = hashlib.sha1(f"{day.date().isoformat()}:{target['id']}".encode("utf-8")).hexdigest()
    offset = int(seed[:8], 16) % (span + 1)
    return start + timedelta(seconds=offset)


def due_targets(now: datetime | None = None) -> list[tuple[datetime, dict]]:
    current = now or config.now_local()
    today = current.date().isoformat()
    due: list[tuple[datetime, dict]] = []
    for target in store.list_targets():
        if not target["enabled"] or not target["schedule_enabled"]:
            continue
        if store.list_runs_for_target_day(int(target["id"]), today):
            continue
        due_at = _scheduled_at(target, current)
        if current >= due_at:
            due.append((due_at, target))
    site_rank = {site: index for index, site in enumerate(config.SITE_ORDER)}
    due.sort(key=lambda item: (item[0], site_rank.get(str(item[1]["site"]), 99), int(item[1]["id"])))
    return due


def dispatch_once() -> int:
    store.init_db()
    settings = store.get_settings()
    count = 0
    for _, target in due_targets():
        result = runtime.run_target(target, trigger_type="dispatch")
        run_id = store.create_run(**result)
        if target["notify_enabled"] and settings.get("wecom_webhook_url"):
            try:
                runtime.send_wecom(
                    settings["wecom_webhook_url"],
                    runtime.build_notification_text(target, result["summary"]),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] wecom push failed target={target['id']}: {exc}", file=sys.stderr)
        count += 1
        time.sleep(runtime.cooldown_seconds(str(target["site"])))
        print(f"target={target['id']} run_id={run_id} summary={result['summary']}")
    return count


def main() -> int:
    lock_path = config.DATA_DIR / "dispatch.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("dispatch already running")
            return 0
        ran = dispatch_once()
        print(f"dispatch_count={ran}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
