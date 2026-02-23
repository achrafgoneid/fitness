from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Real, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DailySummary(Base):
    __tablename__ = "daily_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    recovery_score: Mapped[float | None] = mapped_column(Real, nullable=True)
    hrv: Mapped[float | None] = mapped_column(Real, nullable=True)
    resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_duration_hrs: Mapped[float | None] = mapped_column(Real, nullable=True)
    sleep_quality_score: Mapped[float | None] = mapped_column(Real, nullable=True)
    sleep_deep_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_rem_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_light_mins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    respiratory_rate: Mapped[float | None] = mapped_column(Real, nullable=True)
    whoop_strain: Mapped[float | None] = mapped_column(Real, nullable=True)
    vo2max: Mapped[float | None] = mapped_column(Real, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    garmin_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    strava_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    activity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_mins: Mapped[float | None] = mapped_column(Real, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Real, nullable=True)
    elevation_m: Mapped[float | None] = mapped_column(Real, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_pace_min_km: Mapped[float | None] = mapped_column(Real, nullable=True)
    avg_speed_kmh: Mapped[float | None] = mapped_column(Real, nullable=True)
    hr_zone_1_mins: Mapped[float | None] = mapped_column(Real, nullable=True)
    hr_zone_2_mins: Mapped[float | None] = mapped_column(Real, nullable=True)
    hr_zone_3_mins: Mapped[float | None] = mapped_column(Real, nullable=True)
    hr_zone_4_mins: Mapped[float | None] = mapped_column(Real, nullable=True)
    hr_zone_5_mins: Mapped[float | None] = mapped_column(Real, nullable=True)
    strava_relative_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strava_segment_prs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SyncLog(Base):
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    records_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
