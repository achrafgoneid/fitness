from __future__ import annotations

from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from config import settings
from database import SessionLocal
from sync import sync_garmin, sync_strava, sync_whoop

scheduler = BackgroundScheduler(timezone="UTC")


def run_daily_sync(target_date: date | None = None) -> dict[str, int]:
    day = target_date or (date.today() - timedelta(days=1))
    db = SessionLocal()
    results = {"whoop": 0, "garmin": 0, "strava": 0}
    try:
        for source, fn in (
            ("whoop", sync_whoop),
            ("garmin", sync_garmin),
            ("strava", sync_strava),
        ):
            try:
                results[source] = fn(db, day)
            except Exception as exc:
                print(f"[sync] {source} failed for {day}: {exc}")
    finally:
        db.close()
    print(f"[sync] completed for {day} -> {results}")
    return results


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        run_daily_sync,
        trigger="cron",
        hour=settings.sync_hour,
        minute=settings.sync_minute,
        id="daily_fitness_sync",
        replace_existing=True,
    )
    scheduler.start()
    print(
        f"[scheduler] started daily sync at {settings.sync_hour:02d}:{settings.sync_minute:02d} UTC"
    )


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
