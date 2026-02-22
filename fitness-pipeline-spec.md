# Fitness Data Pipeline — Project Spec

## Overview
A local Python data pipeline that pulls daily fitness data from Whoop, Garmin, and Strava, normalizes it into a unified schema, and stores it in a local SQLite database. Designed for a single user. No frontend for now — just clean, reliable data collection as the foundation for future AI coaching features.

---

## Tech Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI (for OAuth callback handling only)
- **Database**: SQLite (single file, local)
- **ORM**: SQLAlchemy
- **Scheduler**: APScheduler (daily sync at 7am)
- **HTTP client**: httpx
- **Environment variables**: python-dotenv
- **Package manager**: pip + requirements.txt

---

## Project Structure

```
fitness-pipeline/
├── main.py                  # FastAPI app entry point + OAuth routes
├── scheduler.py             # APScheduler daily sync job
├── database.py              # SQLAlchemy setup, engine, session
├── models.py                # SQLAlchemy database models
├── config.py                # Loads env vars via dotenv
├── .env                     # API keys and tokens (never commit this)
├── .env.example             # Template showing required env vars
├── requirements.txt
├── README.md
└── integrations/
    ├── __init__.py
    ├── whoop.py             # Whoop API client
    ├── garmin.py            # Garmin Health API client
    └── strava.py            # Strava API client
```

---

## Data Sources & What To Collect

### Whoop
**Priority data:**
- Daily recovery score (0–100)
- HRV (ms)
- Resting heart rate (bpm)
- Sleep duration (hours)
- Sleep quality score
- Sleep stages (light, deep, REM) in minutes
- Respiratory rate
- Daily strain score

**Auth**: OAuth 2.0
**Base URL**: `https://api.prod.whoop.com/developer/v1`
**Key endpoints**:
- `GET /recovery` — daily recovery + HRV
- `GET /sleep` — sleep data
- `GET /cycle` — strain and activity

---

### Garmin
**Priority data:**
- Activity type (run, ride, swim, strength)
- Activity name
- Distance (km)
- Duration (minutes)
- Average pace (for runs, min/km)
- Average speed (for cycling, km/h)
- Elevation gain (m)
- Average heart rate
- Max heart rate
- Heart rate zones (time in each zone, minutes)
- Calories
- VO2max estimate (when updated)

**Auth**: OAuth 1.0a (note: different from others)
**API**: Garmin Health API (requires app approval from Garmin)
**Key endpoints**:
- `GET /activities` — activity list and summaries
- `GET /dailies` — daily wellness summary
- `GET /epochs` — granular data if needed later

**Note**: Garmin API access requires submitting an application at https://developer.garmin.com. Submit this early as approval can take several days.

---

### Strava
**Priority data:** (used to supplement Garmin, not duplicate)
- Activity ID (for deduplication against Garmin)
- Segment efforts + PRs
- Relative effort score
- Achievement count
- Kudos (optional/fun)

**Auth**: OAuth 2.0
**Base URL**: `https://www.strava.com/api/v3`
**Key endpoints**:
- `GET /athlete/activities` — activity list
- `GET /activities/{id}` — detailed activity including segments

**Deduplication strategy**: Match Strava activities to Garmin activities by date + activity type + duration (within 2 min tolerance). Store both IDs on the activity record.

---

## Database Schema

### Table: `daily_summary`
Stores one row per day aggregating biometric and wellness data.

| Column | Type | Source | Notes |
|---|---|---|---|
| id | INTEGER PK | — | auto |
| date | DATE UNIQUE | — | YYYY-MM-DD |
| recovery_score | REAL | Whoop | 0–100 |
| hrv | REAL | Whoop | ms |
| resting_hr | INTEGER | Whoop | bpm |
| sleep_duration_hrs | REAL | Whoop | |
| sleep_quality_score | REAL | Whoop | 0–100 |
| sleep_deep_mins | INTEGER | Whoop | |
| sleep_rem_mins | INTEGER | Whoop | |
| sleep_light_mins | INTEGER | Whoop | |
| respiratory_rate | REAL | Whoop | breaths/min |
| whoop_strain | REAL | Whoop | 0–21 |
| vo2max | REAL | Garmin | only when updated |
| created_at | DATETIME | — | auto |
| updated_at | DATETIME | — | auto |

---

### Table: `activities`
Stores one row per workout/activity.

| Column | Type | Source | Notes |
|---|---|---|---|
| id | INTEGER PK | — | auto |
| date | DATE | — | |
| garmin_id | TEXT UNIQUE | Garmin | |
| strava_id | TEXT | Strava | nullable |
| activity_type | TEXT | Garmin | run/ride/swim/strength/other |
| name | TEXT | Garmin | activity name |
| duration_mins | REAL | Garmin | |
| distance_km | REAL | Garmin | nullable for strength |
| elevation_m | REAL | Garmin | nullable |
| avg_hr | INTEGER | Garmin | |
| max_hr | INTEGER | Garmin | |
| calories | INTEGER | Garmin | |
| avg_pace_min_km | REAL | Garmin | runs only |
| avg_speed_kmh | REAL | Garmin | cycling only |
| hr_zone_1_mins | REAL | Garmin | |
| hr_zone_2_mins | REAL | Garmin | Zone 2 specifically important |
| hr_zone_3_mins | REAL | Garmin | |
| hr_zone_4_mins | REAL | Garmin | |
| hr_zone_5_mins | REAL | Garmin | |
| strava_relative_effort | INTEGER | Strava | nullable |
| strava_segment_prs | INTEGER | Strava | nullable |
| created_at | DATETIME | — | auto |

---

### Table: `sync_log`
Tracks every sync attempt for debugging.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| sync_date | DATE | date data was pulled for |
| source | TEXT | whoop/garmin/strava |
| status | TEXT | success/failed/partial |
| records_written | INTEGER | |
| error_message | TEXT | nullable |
| ran_at | DATETIME | |

---

### Table: `auth_tokens`
Stores OAuth tokens for each service.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| service | TEXT UNIQUE | whoop/garmin/strava |
| access_token | TEXT | |
| refresh_token | TEXT | |
| expires_at | DATETIME | |
| updated_at | DATETIME | |

---

## OAuth Flow

Each service needs a one-time authorization. FastAPI exposes three routes:

- `GET /auth/strava` → redirects to Strava OAuth
- `GET /auth/strava/callback` → receives code, exchanges for token, stores in DB
- `GET /auth/whoop` → redirects to Whoop OAuth
- `GET /auth/whoop/callback` → receives code, exchanges for token, stores in DB
- `GET /auth/garmin` → redirects to Garmin OAuth
- `GET /auth/garmin/callback` → receives code, exchanges for token, stores in DB

Tokens are stored in the `auth_tokens` table. Each integration module checks token expiry before every API call and refreshes automatically if needed.

---

## Daily Sync Logic

Runs every morning at 7:00am via APScheduler. Pulls data for the previous day (yesterday).

```
scheduler runs at 7:00am
  → sync_whoop(yesterday)
      → fetch recovery, sleep, strain
      → upsert into daily_summary
      → log result to sync_log
  → sync_garmin(yesterday)
      → fetch activities
      → fetch daily wellness (vo2max if updated)
      → upsert into activities + daily_summary
      → log result to sync_log
  → sync_strava(yesterday)
      → fetch activities
      → match to existing garmin activities
      → update strava_id + strava fields on matched records
      → log result to sync_log
```

Each sync step is independent — if Whoop fails, Garmin and Strava still run. All errors are caught, logged to sync_log, and printed to console.

---

## Environment Variables (.env)

```
# Whoop
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=
WHOOP_REDIRECT_URI=http://localhost:8000/auth/whoop/callback

# Garmin
GARMIN_CONSUMER_KEY=
GARMIN_CONSUMER_SECRET=
GARMIN_REDIRECT_URI=http://localhost:8000/auth/garmin/callback

# Strava
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REDIRECT_URI=http://localhost:8000/auth/strava/callback

# App
DATABASE_URL=sqlite:///./fitness.db
SYNC_HOUR=7
SYNC_MINUTE=0
```

---

## Requirements.txt

```
fastapi
uvicorn
sqlalchemy
httpx
apscheduler
python-dotenv
requests-oauthlib  # for Garmin OAuth 1.0a
```

---

## README Instructions

The README should include:
1. How to clone and install dependencies
2. How to register developer apps on Strava, Whoop, and Garmin (with links)
3. How to fill in .env
4. How to run `uvicorn main:app` and complete OAuth for each service
5. How the daily sync works and how to check the sync_log
6. How to query the SQLite database manually using DB Browser for SQLite (free tool)

---

## Future Considerations (not in scope now)
- Frontend dashboard
- Claude AI coaching layer (will query this SQLite database)
- Multi-user support
- Cloud deployment
- Webhooks instead of polling (Strava supports this)
- Training load calculations (ATL/CTL/TSB)
- Goal setting and conflict detection layer
```
