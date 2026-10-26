"""Long-running scheduler: generate and post at fixed local times every day."""

from __future__ import annotations

import time
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .pipeline import auto


def next_run(now: datetime, times: list[str]) -> datetime:
    candidates = []
    for day in (0, 1):
        for hhmm in times:
            h, m = (int(x) for x in hhmm.split(":"))
            t = (now + timedelta(days=day)).replace(hour=h, minute=m, second=0, microsecond=0)
            if t > now:
                candidates.append(t)
    return min(candidates)


def run_forever(cfg: dict, log=print) -> None:
    sch = cfg["schedule"]
    tz = ZoneInfo(sch.get("timezone", "UTC"))
    times = sch["times"]
    if not times:
        raise ValueError("schedule.times is empty")
    log(f"Scheduler started: {', '.join(times)} ({tz.key}); Ctrl+C to stop")
    while True:
        target = next_run(datetime.now(tz), times)
        log(f"Next reel at {target:%Y-%m-%d %H:%M %Z}")
        while (remaining := (target - datetime.now(tz)).total_seconds()) > 0:
            time.sleep(min(remaining, 60))
        try:
            auto(cfg, log=log)
        except Exception:  # keep the schedule alive; the next slot retries
            log("Run failed:\n" + traceback.format_exc())
