from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from integrations import garmin, strava, whoop
from models import Activity, DailySummary, SyncLog


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _upsert_daily_summary(db: Session, target_date: date, fields: dict[str, Any]) -> DailySummary:
    summary = db.query(DailySummary).filter(DailySummary.date == target_date).one_or_none()
    if summary is None:
        summary = DailySummary(date=target_date)
        db.add(summary)
    for key, value in fields.items():
        setattr(summary, key, value)
    db.flush()
    return summary


def _write_sync_log(
    db: Session,
    *,
    target_date: date,
    source: str,
    status: str,
    records_written: int,
    error_message: str | None = None,
) -> None:
    db.add(
        SyncLog(
            sync_date=target_date,
            source=source,
            status=status,
            records_written=records_written,
            error_message=error_message,
            ran_at=datetime.utcnow(),
        )
    )
    db.commit()


def _extract_whoop_metrics(
    recovery_rows: list[dict[str, Any]],
    sleep_rows: list[dict[str, Any]],
    cycle_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if recovery_rows:
        row = recovery_rows[0]
        score = row.get("score", {})
        metrics["recovery_score"] = _as_float(score.get("recovery_score"))
        metrics["hrv"] = _as_float(score.get("hrv_rmssd_milli"))
        metrics["resting_hr"] = _as_int(score.get("resting_heart_rate"))
    if sleep_rows:
        row = sleep_rows[0]
        score = row.get("score", {})
        stage_summary = score.get("stage_summary", {})
        respiratory = score.get("respiratory_rate")
        metrics["sleep_duration_hrs"] = _as_float(score.get("sleep_needed")) / 3600 if score.get("sleep_needed") else None
        metrics["sleep_quality_score"] = _as_float(score.get("sleep_performance_percentage"))
        metrics["sleep_deep_mins"] = _as_int(stage_summary.get("total_slow_wave_sleep_time_milli"))
        if metrics["sleep_deep_mins"] is not None:
            metrics["sleep_deep_mins"] = int(metrics["sleep_deep_mins"] / 60000)
        metrics["sleep_rem_mins"] = _as_int(stage_summary.get("total_rem_sleep_time_milli"))
        if metrics["sleep_rem_mins"] is not None:
            metrics["sleep_rem_mins"] = int(metrics["sleep_rem_mins"] / 60000)
        metrics["sleep_light_mins"] = _as_int(stage_summary.get("total_light_sleep_time_milli"))
        if metrics["sleep_light_mins"] is not None:
            metrics["sleep_light_mins"] = int(metrics["sleep_light_mins"] / 60000)
        metrics["respiratory_rate"] = _as_float(respiratory)
    if cycle_rows:
        row = cycle_rows[0]
        score = row.get("score", {})
        metrics["whoop_strain"] = _as_float(score.get("strain"))
    return metrics


def sync_whoop(db: Session, target_date: date) -> int:
    source = "whoop"
    try:
        recovery_rows = whoop.fetch_recovery(db, target_date)
        sleep_rows = whoop.fetch_sleep(db, target_date)
        cycle_rows = whoop.fetch_cycle(db, target_date)
        metrics = _extract_whoop_metrics(recovery_rows, sleep_rows, cycle_rows)
        _upsert_daily_summary(db, target_date, metrics)
        db.commit()
        records_written = 1 if metrics else 0
        _write_sync_log(
            db,
            target_date=target_date,
            source=source,
            status="success",
            records_written=records_written,
        )
        return records_written
    except Exception as exc:
        db.rollback()
        _write_sync_log(
            db,
            target_date=target_date,
            source=source,
            status="failed",
            records_written=0,
            error_message=str(exc),
        )
        return 0


def _garmin_activity_type(raw: dict[str, Any]) -> str:
    value = (raw.get("activityType") or raw.get("activity_type") or "other").lower()
    if "run" in value:
        return "run"
    if "ride" in value or "cycle" in value or "bike" in value:
        return "ride"
    if "swim" in value:
        return "swim"
    if "strength" in value:
        return "strength"
    return "other"


def _upsert_activity_from_garmin(db: Session, raw: dict[str, Any], target_date: date) -> Activity:
    garmin_id = str(raw.get("activityId") or raw.get("activity_id") or "")
    if not garmin_id:
        raise ValueError("Garmin activity missing id")

    activity = db.query(Activity).filter(Activity.garmin_id == garmin_id).one_or_none()
    if activity is None:
        activity = Activity(garmin_id=garmin_id, date=target_date)
        db.add(activity)

    duration_seconds = _as_float(raw.get("durationInSeconds") or raw.get("duration"))
    distance_meters = _as_float(raw.get("distanceInMeters") or raw.get("distance"))
    avg_speed_mps = _as_float(raw.get("averageSpeedInMetersPerSecond") or raw.get("averageSpeed"))

    activity.activity_type = _garmin_activity_type(raw)
    activity.name = raw.get("activityName") or raw.get("activity_name")
    activity.duration_mins = (duration_seconds / 60.0) if duration_seconds is not None else None
    activity.distance_km = (distance_meters / 1000.0) if distance_meters is not None else None
    activity.elevation_m = _as_float(raw.get("elevationGainInMeters") or raw.get("elevationGain"))
    activity.avg_hr = _as_int(raw.get("averageHR") or raw.get("averageHeartRate"))
    activity.max_hr = _as_int(raw.get("maxHR") or raw.get("maxHeartRate"))
    activity.calories = _as_int(raw.get("activeKilocalories") or raw.get("calories"))

    if activity.activity_type == "run" and activity.distance_km and activity.duration_mins:
        activity.avg_pace_min_km = activity.duration_mins / activity.distance_km
    elif activity.activity_type == "ride" and avg_speed_mps is not None:
        activity.avg_speed_kmh = avg_speed_mps * 3.6

    zones = raw.get("heartRateZones") or raw.get("hrZones") or {}
    if isinstance(zones, dict):
        activity.hr_zone_1_mins = _as_float(zones.get("zone1")) or _as_float(zones.get("z1"))
        activity.hr_zone_2_mins = _as_float(zones.get("zone2")) or _as_float(zones.get("z2"))
        activity.hr_zone_3_mins = _as_float(zones.get("zone3")) or _as_float(zones.get("z3"))
        activity.hr_zone_4_mins = _as_float(zones.get("zone4")) or _as_float(zones.get("z4"))
        activity.hr_zone_5_mins = _as_float(zones.get("zone5")) or _as_float(zones.get("z5"))

    db.flush()
    return activity


def sync_garmin(db: Session, target_date: date) -> int:
    source = "garmin"
    try:
        activities = garmin.fetch_activities(db, target_date)
        dailies = garmin.fetch_dailies(db, target_date)
        records_written = 0
        for raw in activities:
            _upsert_activity_from_garmin(db, raw, target_date)
            records_written += 1

        if dailies:
            daily = dailies[0]
            vo2max = _as_float(daily.get("vO2MaxValue") or daily.get("vo2max"))
            if vo2max is not None:
                _upsert_daily_summary(db, target_date, {"vo2max": vo2max})

        db.commit()
        _write_sync_log(
            db,
            target_date=target_date,
            source=source,
            status="success",
            records_written=records_written,
        )
        return records_written
    except Exception as exc:
        db.rollback()
        _write_sync_log(
            db,
            target_date=target_date,
            source=source,
            status="failed",
            records_written=0,
            error_message=str(exc),
        )
        return 0


def _same_activity_type(strava_type: str | None, garmin_type: str | None) -> bool:
    if not strava_type or not garmin_type:
        return False
    s = strava_type.lower()
    g = garmin_type.lower()
    if "run" in s and g == "run":
        return True
    if ("ride" in s or "cycle" in s) and g == "ride":
        return True
    if "swim" in s and g == "swim":
        return True
    if "workout" in s and g == "strength":
        return True
    return s == g


def _find_garmin_match(db: Session, target_date: date, raw: dict[str, Any]) -> Activity | None:
    duration_mins = _as_float(raw.get("moving_time"))
    if duration_mins is None:
        return None
    duration_mins = duration_mins / 60.0

    candidates = db.query(Activity).filter(Activity.date == target_date).all()
    for activity in candidates:
        if not _same_activity_type(raw.get("type"), activity.activity_type):
            continue
        if activity.duration_mins is None:
            continue
        if abs(activity.duration_mins - duration_mins) <= 2.0:
            return activity
    return None


def sync_strava(db: Session, target_date: date) -> int:
    source = "strava"
    try:
        activities = strava.fetch_activities(db, target_date)
        records_written = 0
        for raw in activities:
            match = _find_garmin_match(db, target_date, raw)
            if match is None:
                continue
            detail = strava.fetch_activity_detail(db, str(raw.get("id")))
            match.strava_id = str(raw.get("id"))
            match.strava_relative_effort = _as_int(detail.get("relative_effort"))
            achievements = detail.get("achievement_count")
            if achievements is None and isinstance(detail.get("segment_efforts"), list):
                achievements = sum(
                    int(effort.get("achievements", 0) or 0)
                    for effort in detail["segment_efforts"]
                    if isinstance(effort, dict)
                )
            match.strava_segment_prs = _as_int(achievements)
            records_written += 1
        db.commit()
        _write_sync_log(
            db,
            target_date=target_date,
            source=source,
            status="success",
            records_written=records_written,
        )
        return records_written
    except Exception as exc:
        db.rollback()
        _write_sync_log(
            db,
            target_date=target_date,
            source=source,
            status="failed",
            records_written=0,
            error_message=str(exc),
        )
        return 0
