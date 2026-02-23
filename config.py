from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    whoop_client_id: str = os.getenv("WHOOP_CLIENT_ID", "")
    whoop_client_secret: str = os.getenv("WHOOP_CLIENT_SECRET", "")
    whoop_redirect_uri: str = os.getenv(
        "WHOOP_REDIRECT_URI", "http://localhost:8000/auth/whoop/callback"
    )

    garmin_consumer_key: str = os.getenv("GARMIN_CONSUMER_KEY", "")
    garmin_consumer_secret: str = os.getenv("GARMIN_CONSUMER_SECRET", "")
    garmin_redirect_uri: str = os.getenv(
        "GARMIN_REDIRECT_URI", "http://localhost:8000/auth/garmin/callback"
    )

    strava_client_id: str = os.getenv("STRAVA_CLIENT_ID", "")
    strava_client_secret: str = os.getenv("STRAVA_CLIENT_SECRET", "")
    strava_redirect_uri: str = os.getenv(
        "STRAVA_REDIRECT_URI", "http://localhost:8000/auth/strava/callback"
    )

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./fitness.db")
    sync_hour: int = int(os.getenv("SYNC_HOUR", "7"))
    sync_minute: int = int(os.getenv("SYNC_MINUTE", "0"))


settings = Settings()
