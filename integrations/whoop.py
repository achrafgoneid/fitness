from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from config import settings
from models import AuthToken

WHOOP_BASE_URL = "https://api.prod.whoop.com/developer/v1"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"


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


def get_whoop_token(db: Session) -> AuthToken:
    token = db.query(AuthToken).filter(AuthToken.service == "whoop").one_or_none()
    if token is None:
        raise RuntimeError("Whoop token is missing. Run /auth/whoop first.")
    return token


def refresh_whoop_token_if_needed(db: Session) -> AuthToken:
    token = get_whoop_token(db)
    if not _expires_soon(token.expires_at):
        return token
    if not token.refresh_token:
        raise RuntimeError("Whoop token expired and refresh token is missing.")

    payload = {
        "client_id": settings.whoop_client_id,
        "client_secret": settings.whoop_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
    }
    response = httpx.post(WHOOP_TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    token_data = response.json()
    token.access_token = token_data["access_token"]
    token.refresh_token = token_data.get("refresh_token", token.refresh_token)
    expires_in = int(token_data.get("expires_in", 3600))
    token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    token.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(token)
    return token


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _date_params(target_date: date) -> dict[str, str]:
    day = target_date.isoformat()
    return {"start_date": day, "end_date": day}


def fetch_recovery(db: Session, target_date: date) -> list[dict[str, Any]]:
    token = refresh_whoop_token_if_needed(db)
    response = httpx.get(
        f"{WHOOP_BASE_URL}/recovery",
        headers=_auth_headers(token.access_token),
        params=_date_params(target_date),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("records", [])


def fetch_sleep(db: Session, target_date: date) -> list[dict[str, Any]]:
    token = refresh_whoop_token_if_needed(db)
    response = httpx.get(
        f"{WHOOP_BASE_URL}/sleep",
        headers=_auth_headers(token.access_token),
        params=_date_params(target_date),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("records", [])


def fetch_cycle(db: Session, target_date: date) -> list[dict[str, Any]]:
    token = refresh_whoop_token_if_needed(db)
    response = httpx.get(
        f"{WHOOP_BASE_URL}/cycle",
        headers=_auth_headers(token.access_token),
        params=_date_params(target_date),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("records", [])
