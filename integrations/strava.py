from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from config import settings
from models import AuthToken

STRAVA_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _expires_soon(expires_at: datetime | None, *, margin_seconds: int = 90) -> bool:
    expires_at_utc = _as_utc(expires_at)
    if expires_at_utc is None:
        return False
    return expires_at_utc <= datetime.now(timezone.utc) + timedelta(seconds=margin_seconds)


def get_strava_token(db: Session) -> AuthToken:
    token = db.query(AuthToken).filter(AuthToken.service == "strava").one_or_none()
    if token is None:
        raise RuntimeError("Strava token is missing. Run /auth/strava first.")
    return token


def refresh_strava_token_if_needed(db: Session) -> AuthToken:
    token = get_strava_token(db)
    if not _expires_soon(token.expires_at):
        return token
    if not token.refresh_token:
        raise RuntimeError("Strava token expired and refresh token is missing.")

    payload = {
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
    }
    response = httpx.post(STRAVA_TOKEN_URL, data=payload, timeout=30, trust_env=False)
    response.raise_for_status()
    token_data = response.json()
    token.access_token = token_data["access_token"]
    token.refresh_token = token_data.get("refresh_token", token.refresh_token)
    expires_at = token_data.get("expires_at")
    if expires_at is not None:
        token.expires_at = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)
    token.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(token)
    return token


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def fetch_activities(db: Session, target_date: date) -> list[dict[str, Any]]:
    token = refresh_strava_token_if_needed(db)
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    params = {
        "after": int(day_start.timestamp()),
        "before": int(day_end.timestamp()),
        "per_page": 200,
        "page": 1,
    }
    response = httpx.get(
        f"{STRAVA_BASE_URL}/athlete/activities",
        headers=_auth_headers(token.access_token),
        params=params,
        timeout=30,
        trust_env=False,
    )
    response.raise_for_status()
    return response.json()


def fetch_activity_detail(db: Session, activity_id: str) -> dict[str, Any]:
    token = refresh_strava_token_if_needed(db)
    response = httpx.get(
        f"{STRAVA_BASE_URL}/activities/{activity_id}",
        headers=_auth_headers(token.access_token),
        timeout=30,
        trust_env=False,
    )
    response.raise_for_status()
    return response.json()
