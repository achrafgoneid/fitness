from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from requests_oauthlib import OAuth1Session
from sqlalchemy.orm import Session

from config import settings
from database import get_db, init_db
from models import AuthToken
from scheduler import run_daily_sync, shutdown_scheduler, start_scheduler

app = FastAPI(title="Fitness Data Pipeline")

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"

GARMIN_REQUEST_TOKEN_URL = "https://connectapi.garmin.com/oauth-service/oauth/request_token"
GARMIN_AUTHORIZE_URL = "https://connectapi.garmin.com/oauthConfirm"
GARMIN_ACCESS_TOKEN_URL = "https://connectapi.garmin.com/oauth-service/oauth/access_token"

# Single-user local cache for the OAuth 1.0a temporary secret.
GARMIN_TEMP_SECRETS: dict[str, str] = {}


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
    return None


def upsert_token(
    db: Session,
    *,
    service: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    token = db.query(AuthToken).filter(AuthToken.service == service).one_or_none()
    now = datetime.now(timezone.utc)
    if token is None:
        token = AuthToken(
            service=service,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            updated_at=now,
        )
        db.add(token)
    else:
        token.access_token = access_token
        token.refresh_token = refresh_token
        token.expires_at = expires_at
        token.updated_at = now
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    shutdown_scheduler()


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sync/run")
def run_sync_for_date(
    target_date: str | None = Query(default=None, description="YYYY-MM-DD, defaults to yesterday"),
) -> dict[str, Any]:
    sync_date = None
    if target_date:
        sync_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    return {"date": str(sync_date) if sync_date else "yesterday", "results": run_daily_sync(sync_date)}


@app.get("/auth/strava")
def auth_strava() -> RedirectResponse:
    redirect_url = (
        f"{STRAVA_AUTH_URL}"
        f"?client_id={settings.strava_client_id}"
        "&response_type=code"
        f"&redirect_uri={settings.strava_redirect_uri}"
        "&approval_prompt=auto"
        "&scope=activity:read_all,read"
    )
    return RedirectResponse(url=redirect_url)


@app.get("/auth/strava/callback")
def auth_strava_callback(
    code: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    payload = {
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    response = httpx.post(STRAVA_TOKEN_URL, data=payload, timeout=30)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Strava token exchange failed: {response.text}")
    token_data = response.json()
    expires_at = _to_datetime(token_data.get("expires_at"))
    upsert_token(
        db,
        service="strava",
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
    )
    return {"message": "Strava authorization successful."}


@app.get("/auth/whoop")
def auth_whoop() -> RedirectResponse:
    redirect_url = (
        f"{WHOOP_AUTH_URL}"
        f"?client_id={settings.whoop_client_id}"
        "&response_type=code"
        f"&redirect_uri={settings.whoop_redirect_uri}"
        "&scope=offline+read:cycles+read:recovery+read:sleep"
    )
    return RedirectResponse(url=redirect_url)


@app.get("/auth/whoop/callback")
def auth_whoop_callback(
    code: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    payload = {
        "client_id": settings.whoop_client_id,
        "client_secret": settings.whoop_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.whoop_redirect_uri,
    }
    response = httpx.post(WHOOP_TOKEN_URL, data=payload, timeout=30)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Whoop token exchange failed: {response.text}")
    token_data = response.json()
    expires_in = token_data.get("expires_in")
    expires_at = None
    if expires_in is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    upsert_token(
        db,
        service="whoop",
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
    )
    return {"message": "Whoop authorization successful."}


@app.get("/auth/garmin")
def auth_garmin() -> RedirectResponse:
    oauth = OAuth1Session(
        settings.garmin_consumer_key,
        client_secret=settings.garmin_consumer_secret,
        callback_uri=settings.garmin_redirect_uri,
    )
    response_text = oauth.fetch_request_token(GARMIN_REQUEST_TOKEN_URL)
    request_token = response_text["oauth_token"]
    request_secret = response_text["oauth_token_secret"]
    GARMIN_TEMP_SECRETS[request_token] = request_secret
    return RedirectResponse(url=f"{GARMIN_AUTHORIZE_URL}?oauth_token={request_token}")


@app.get("/auth/garmin/callback")
def auth_garmin_callback(
    oauth_token: str = Query(...),
    oauth_verifier: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    temp_secret = GARMIN_TEMP_SECRETS.pop(oauth_token, None)
    if temp_secret is None:
        raise HTTPException(status_code=400, detail="Garmin temporary token was not found.")

    oauth = OAuth1Session(
        settings.garmin_consumer_key,
        client_secret=settings.garmin_consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=temp_secret,
        verifier=oauth_verifier,
    )
    response = oauth.fetch_access_token(GARMIN_ACCESS_TOKEN_URL)
    access_token = response["oauth_token"]
    token_secret = response["oauth_token_secret"]
    upsert_token(
        db,
        service="garmin",
        access_token=access_token,
        refresh_token=token_secret,
        expires_at=None,
    )
    return {"message": "Garmin authorization successful."}
