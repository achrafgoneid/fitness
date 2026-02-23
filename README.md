# fitness

Aggregating fitness data from different sources into one local SQLite database.

## What this project does

This project runs a local Python data pipeline that:
- authenticates with Whoop, Garmin, and Strava,
- pulls daily fitness data,
- normalizes it into a shared schema,
- stores it in SQLite,
- and logs every sync run in `sync_log`.

The app is backend-only for now (no frontend).

## 1) Clone and install

```bash
git clone https://github.com/achrafgoneid/fitness.git
cd fitness
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Register developer apps

Create apps and credentials for each provider:

- Strava API: https://developers.strava.com
- Whoop Developer Portal: https://developer.whoop.com
- Garmin Health API: https://developer.garmin.com/gc-developer-program/health-api/

Garmin approval can take time, so apply early.

## 3) Configure environment variables

```bash
cp .env.example .env
```

Fill in all values in `.env`:
- `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`
- `GARMIN_CONSUMER_KEY`, `GARMIN_CONSUMER_SECRET`
- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`
- optionally adjust `DATABASE_URL`, `SYNC_HOUR`, `SYNC_MINUTE`

Default callback URLs:
- `http://localhost:8000/auth/whoop/callback`
- `http://localhost:8000/auth/garmin/callback`
- `http://localhost:8000/auth/strava/callback`

Use exactly those URLs in your provider app settings unless you intentionally change them in `.env`.

## 4) Run API and complete OAuth

Start the app:

```bash
uvicorn main:app --reload
```

Then authorize each service in a browser:
- `http://localhost:8000/auth/whoop`
- `http://localhost:8000/auth/garmin`
- `http://localhost:8000/auth/strava`

Each callback stores credentials in `auth_tokens`.

## 5) How daily sync works

The scheduler runs daily at `SYNC_HOUR:SYNC_MINUTE` (UTC) and syncs **yesterday**:
- `sync_whoop(yesterday)` -> upserts `daily_summary`
- `sync_garmin(yesterday)` -> upserts `activities` and VO2max in `daily_summary`
- `sync_strava(yesterday)` -> matches Garmin activities and enriches with Strava fields

Each source runs independently. If one fails, others still run.
Every attempt writes one row to `sync_log`.

Manual run endpoint:

```bash
curl -X POST "http://localhost:8000/sync/run"
curl -X POST "http://localhost:8000/sync/run?target_date=2026-02-22"
```

## 6) Check data and logs

Quick table checks:

```bash
sqlite3 fitness.db "SELECT * FROM sync_log ORDER BY ran_at DESC LIMIT 20;"
sqlite3 fitness.db "SELECT * FROM daily_summary ORDER BY date DESC LIMIT 10;"
sqlite3 fitness.db "SELECT * FROM activities ORDER BY date DESC LIMIT 20;"
```

You can also open `fitness.db` in **DB Browser for SQLite**:
https://sqlitebrowser.org/
