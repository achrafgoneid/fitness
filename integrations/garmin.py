from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from requests_oauthlib import OAuth1Session
from sqlalchemy.orm import Session

from config import settings
from models import AuthToken

GARMIN_BASE_URL = "https://healthapi.garmin.com/wellness-api/rest"


def get_garmin_token(db: Session) -> AuthToken:
    token = db.query(AuthToken).filter(AuthToken.service == "garmin").one_or_none()
    if token is None:
        raise RuntimeError("Garmin token is missing. Run /auth/garmin first.")
    return token


def _oauth_session(db: Session) -> OAuth1Session:
    token = get_garmin_token(db)
    return OAuth1Session(
        settings.garmin_consumer_key,
        client_secret=settings.garmin_consumer_secret,
        resource_owner_key=token.access_token,
        resource_owner_secret=token.refresh_token or "",
    )


def fetch_activities(db: Session, target_date: date) -> list[dict[str, Any]]:
    oauth = _oauth_session(db)
    start_ts = int(datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())
    response = oauth.get(
        f"{GARMIN_BASE_URL}/activities",
        params={"uploadStartTimeInSeconds": start_ts},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_dailies(db: Session, target_date: date) -> list[dict[str, Any]]:
    oauth = _oauth_session(db)
    start_ts = int(datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())
    response = oauth.get(
        f"{GARMIN_BASE_URL}/dailies",
        params={"summaryStartTimeInSeconds": start_ts},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return data
    return [data] if data else []
