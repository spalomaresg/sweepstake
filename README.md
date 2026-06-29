# World Cup 2026 Sweepstake

An internal office sweepstake app for the FIFA World Cup 2026. Built with Django and SQLite. Colleagues predict match results, earn points, and compete on a leaderboard — individually and by team.

The interface is fully responsive — desktop and mobile are both supported. Match kickoff times are displayed in the browser's local timezone.

---

## Requirements

- Python 3.10+
- pip
- `gettext` (only needed to recompile translations — usually pre-installed on Linux/macOS)

---

## Setup

### 1. Extract and install

```bash
tar -xzf worldcup_sweepstake.tar.gz
cd worldcup_sweepstake
pip install -r requirements.txt
```

### 2. Create a `.env` file

Create a `.env` file in the project root (next to `manage.py`). This file is gitignored and must be created on each environment:

```env
SECRET_KEY=replace-this-with-a-long-random-string
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,your-server-ip
LANGUAGE=en
```

For local development:

```env
SECRET_KEY=any-local-dev-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
LANGUAGE=en
```

Generate a secure secret key with:

```bash
python manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

#### `.env` variables reference

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Django secret key (required) |
| `DEBUG` | `False` | Enable Django debug mode |
| `ALLOWED_HOSTS` | — | Comma-separated list of allowed hosts |
| `LANGUAGE` | `en` | Interface language — `en` (English) or `es` (Spanish) |

### 3. API key (football-data.org)

Match results are synced automatically from [football-data.org](https://www.football-data.org). The key is set directly in `worldcup_sweepstake/settings.py`:

```python
FOOTBALL_DATA_API_KEY = 'your-api-key-here'
```

Sign up for a free key at football-data.org (no credit card required). The free tier allows 10 requests/minute, which is more than enough.

### 4. Initialise the database

```bash
python manage.py migrate
```

### 5. Configure sweepstake teams (optional)

If you want team-based competition, edit `teams.csv` in the project root — one row per office team:

```csv
team,color
Intel,#6366F1
HR & Finance,#EC4899
```

Then load them:

```bash
python manage.py load_teams
```

Safe to re-run — uses `update_or_create` so existing teams are updated, not duplicated.

If no teams are loaded, the team selector is hidden on the registration page and the Teams tab is hidden on the leaderboard.

### 6. Load World Cup group stage data

```bash
python manage.py load_data
```

Loads all 48 national teams and 72 group stage matches with official kickoff times sourced from the football-data.org API.

### 7. Create an admin account

```bash
python manage.py createsuperuser
```

### 8. Run the server

```bash
python manage.py runserver
```

Or with a specific host/port:

```bash
python manage.py runserver 0.0.0.0:8000
```

---

## Admin panel

Access at `/admin/` with your superuser credentials.

### Setting up users

#### Invite list

Before anyone can register, add their details to `valid_emails.csv` in the project root:

```csv
email,invite_code
alice@example.com,ALICE2026
bob@example.com,BOB2026
```

- **email** — the exact email address the user will register with (case-insensitive)
- **invite_code** — a code you share with each user privately; they must enter it during registration

Users cannot register without both a matching email and the correct invite code. The same check applies at login — if an email is removed from the CSV, that user can no longer sign in.

Supports both comma (`,`) and semicolon (`;`) delimiters — the format is detected automatically.

#### After registration

Once registered, go to **Admin → Users**, open each user's profile and:

- Optionally assign them to a **Sweepstake Team**
- Tick **Excluded from team stats** if you want to exclude them from leaderboard calculations (e.g. test accounts)

Team assignment is optional — if no users have teams, the Teams leaderboard tab is hidden automatically.

### Managing matches

Go to **Admin → Matches** to:

- Add knockout round matches manually once the bracket is known (or let `sync_results` create them automatically from the API)
- Enter match results (home goals, away goals)
- For knockout matches that go to extra time / penalties:
  - Set `home_goals` and `away_goals` to the 90-minute score
  - Set `knockout_winner` to `home` or `away` (who advanced)
- Tick **Finished** to finalise the match — points are recalculated automatically for all predictions

### Managing sweepstake teams

Go to **Admin → Sweepstake Teams** to create, rename, or recolour teams. Each team gets a hex colour used on the leaderboard.

---

## Scoring rules

| Phase | Correct winner | Exact score |
|---|---|---|
| Group Stage | 1 pt | — |
| Round of 32 | 1 pt | +2 pts |
| Round of 16 | 1 pt | +2 pts |
| Quarter-finals | 1 pt | +2 pts |
| Semi-finals | 2 pts | +4 pts |
| Third Place | 2 pts | +4 pts |
| Final | 5 pts | +10 pts |

Exact score points are **cumulative** — if you predict the exact score you get both the winner points and the exact score points.

For knockout matches, the "winner" is whoever advances (after extra time / penalties if needed). The exact score is always based on the 90-minute result.

---

## Phase and betting rules

- Users can only place predictions on the **current active phase**
- A phase opens once all matches from the previous phase are marked as finished
- **Exception:** Third Place and Final both open simultaneously once all Semi-finals are finished
- Predictions can be changed freely until the match kicks off — after that they are locked

---

## Management commands

### Load group stage data

```bash
python manage.py load_data
```

Loads 48 national teams (with flags) and 72 group stage matches. Safe to re-run — uses `update_or_create` so existing data is not duplicated.

---

### Sync match results and create fixtures

Fetches data from the football-data.org API:

- **Finished matches** — updates scores and recalculates points for all affected predictions
- **Upcoming knockout matches** — creates fixtures in the database once the API publishes the bracket (after each round completes)

```bash
python manage.py sync_results
```

Preview without saving:

```bash
python manage.py sync_results --dry-run
```

Override the competition code if needed (default: `WC`):

```bash
python manage.py sync_results --competition WC
```

---

### Start the result sync scheduler (production only)

Long-running process that automatically runs `sync_results` at timed intervals after each match. Refuses to start when `DEBUG=True`.

```bash
python manage.py start_sync_scheduler
```

Sync schedule per match (relative to expected final whistle = kickoff + 90 min):

| Offset | Purpose |
|---|---|
| +10 min | Catches most matches that end on time |
| +30 min | Catches matches with extra time |
| +1 hour | Catches delayed or VAR-heavy games |
| +2 hours | Final catch-all |

When no matches are pending (e.g. between phases), the scheduler calls `sync_results` once per hour to pick up newly published knockout fixtures from the API.

In production this runs as a systemd service — see [Deployment](#deploying-to-a-server-nginx--gunicorn) below.

---

### Create knockout fixtures

Creates match fixtures for a knockout phase based on actual results — no results are simulated. Run this once each round's bracket is determined.

For **Round of 32**: resolves teams automatically from the group stage standings using the official FIFA bracket (group winners, runners-up, and best 8 third-place teams).

For **later rounds**: pairs up winners from the previous finished phase.

```bash
python manage.py create_fixture round_of_32
python manage.py create_fixture round_of_16
python manage.py create_fixture quarterfinals
python manage.py create_fixture semifinals
python manage.py create_fixture third_place
python manage.py create_fixture final
```

> **Note:** `sync_results` also creates upcoming knockout fixtures automatically once the API publishes the bracket. Use `create_fixture` if you prefer to create them manually or if the API hasn't published them yet.

---

### Simulate a phase (testing only)

Useful for testing scoring, bracket progression, and UI without waiting for real matches.

```bash
# Simulate a specific phase (random results)
python manage.py simulate_phase group_stage
python manage.py simulate_phase round_of_32
python manage.py simulate_phase round_of_16
python manage.py simulate_phase quarterfinals
python manage.py simulate_phase semifinals
python manage.py simulate_phase third_place
python manage.py simulate_phase final

# Simulate the entire tournament end-to-end
python manage.py simulate_phase all

# Use a fixed random seed for reproducible results
python manage.py simulate_phase group_stage --seed 42

# Only create the bracket matches without simulating results
# (lets users place predictions before results are entered)
python manage.py simulate_phase round_of_32 --create-only

# Reset results for a phase (undo simulation)
python manage.py simulate_phase group_stage --reset
```

**Note:** In production, knockout fixtures are created automatically by `sync_results` once the API publishes the bracket.

**Tip:** After simulating the group stage, run `simulate_phase round_of_32 --create-only` to create the R32 fixtures (so users can bet) before entering real results.

---

### Reset match data

To wipe all matches (and their predictions) and start fresh:

```bash
python manage.py shell -c "from bets.models import Match; count, _ = Match.objects.all().delete(); print(f'Deleted {count} records')"
python manage.py load_data
python manage.py sync_results   # picks up any knockout fixtures already published
```

> ⚠️ This deletes all user predictions (cascade). Only do this before the tournament starts or if the data is wrong.

---

## URL reference

| URL | Description |
|---|---|
| `/` | Home / landing page |
| `/register/` | User registration (requires invite email and code) |
| `/login/` | Sign in |
| `/logout/` | Sign out |
| `/leaderboard/` | Individual and team leaderboard with per-phase breakdown |
| `/my-predictions/` | Place and manage your predictions |
| `/standings/` | Live group stage standings |
| `/admin/` | Django admin panel |

---

## Project structure

```
worldcup_sweepstake/
├── bets/                          # Main Django app
│   ├── migrations/                # Database migrations
│   ├── management/
│   │   └── commands/
│   │       ├── load_data.py           # Load teams and group stage fixtures
│   │       ├── load_teams.py          # Load sweepstake teams from teams.csv
│   │       ├── sync_results.py        # Sync results + create knockout fixtures
│   │       ├── create_fixture.py      # Create knockout fixtures from actual standings
│   │       ├── start_sync_scheduler.py# Production: auto-sync after each match
│   │       └── simulate_phase.py      # Testing: simulate match results
│   ├── models.py                  # Data models
│   ├── views.py                   # Request handlers
│   ├── forms.py                   # Registration and prediction forms
│   ├── admin.py                   # Admin panel configuration
│   ├── context_processors.py      # Injects web_title into all templates
│   └── templatetags/
│       └── bet_extras.py          # Custom template filters
├── templates/
│   └── bets/                      # HTML templates
│       ├── base.html
│       ├── home.html
│       ├── register.html
│       ├── login.html
│       ├── leaderboard.html
│       ├── my_predictions.html
│       └── group_standings.html
├── locale/
│   └── es/
│       └── LC_MESSAGES/
│           ├── django.po          # Spanish translations (source)
│           └── django.mo          # Compiled translations (generated)
├── worldcup_sweepstake/           # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── valid_emails.csv               # Invite list (email + invite code per user)
├── teams.csv                      # Sweepstake teams definition (optional)
├── .env                           # Local config — gitignored, create manually
├── manage.py
├── requirements.txt
└── README.md
```

---

## Internationalisation

The interface supports English (`en`) and Spanish (`es`), controlled by the `LANGUAGE` variable in `.env`. All user-visible strings in templates, forms, and views are translated.

To add a new language:

1. Create `locale/<lang>/LC_MESSAGES/django.po` (copy `locale/es/django.po` as a template)
2. Fill in the `msgstr` entries
3. Compile: `python manage.py compilemessages --locale=<lang>`
4. Set `LANGUAGE=<lang>` in `.env`

To recompile after editing an existing `.po` file:

```bash
python manage.py compilemessages --locale=es
```

---

## Deploying to a server (nginx + gunicorn)

### Install gunicorn

```bash
pip install gunicorn
```

### Collect static files

```bash
python manage.py collectstatic
```

### Run with gunicorn

```bash
gunicorn worldcup_sweepstake.wsgi:application --bind 0.0.0.0:8000
```

### Example nginx config

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location /static/ {
        alias /path/to/worldcup_sweepstake/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Automatic result syncing (systemd service)

Create `/etc/systemd/system/django-sweepstake-sync.service`, replacing `django-sweepstake` with your main service name:

```ini
[Unit]
Description=World Cup result sync scheduler
After=network.target
BindsTo=django-sweepstake.service

[Service]
Type=simple
WorkingDirectory=/path/to/worldcup_sweepstake
ExecStart=/path/to/worldcup_sweepstake/.venv/bin/python manage.py start_sync_scheduler
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`BindsTo=django-sweepstake.service` ties the sync scheduler to your main Django service — it starts and stops automatically alongside it.

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now django-sweepstake-sync.service

# Verify both are running
sudo systemctl status django-sweepstake django-sweepstake-sync

# Watch sync logs live
sudo journalctl -u django-sweepstake-sync.service -f
```

From then on, `systemctl start django-sweepstake` brings up both services, and `systemctl stop django-sweepstake` stops both.

The scheduler only starts when `DEBUG=False`. It sleeps until the next scheduled sync time and wakes up automatically — no polling overhead between matches.

---

## Timezone

All kickoff times are stored in UTC. Match times are displayed in the **browser's local timezone** via JavaScript — each user sees times converted to their own timezone automatically.
