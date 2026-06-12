# ThreatFabric World Cup 2026 Sweepstake

An internal office sweepstake app for the FIFA World Cup 2026. Built with Django and SQLite. Colleagues predict match results, earn points, and compete on a leaderboard — individually and by team.

---

## Requirements

- Python 3.10+
- pip

---

## Setup

### 1. Extract and install

```bash
tar -xzf worldcup_sweepstake.tar.gz
cd worldcup_sweepstake
pip install -r requirements.txt
```

### 2. Configure for production

Open `worldcup_sweepstake/settings.py` and update:

```python
SECRET_KEY = 'replace-this-with-a-long-random-string'
DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com', 'your-server-ip']
```

### 3. Initialise the database

```bash
python manage.py migrate
```

### 4. Configure sweepstake teams

Edit `teams.csv` in the project root — one row per office team:

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

### 5. Load World Cup group stage data

```bash
python manage.py load_data
```

Loads all 48 national teams and 72 group stage matches with official kickoff times (UTC).

### 6. Create an admin account

```bash
python manage.py createsuperuser
```

### 7. Run the server

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
alice@threatfabric.com,ALICE2026
bob@threatfabric.com,BOB2026
```

- **email** — the exact email address the user will register with (case-insensitive)
- **invite_code** — a code you share with each user privately; they must enter it during registration

Users cannot register without both a matching email and the correct invite code. The same check applies at login — if an email is removed from the CSV, that user can no longer sign in.

2. Once registered, go to **Admin → Users**, open each user's profile and:
   - Assign them to a **Sweepstake Team**
   - Tick **Excluded from team stats** if you want to exclude them from leaderboard calculations (e.g. test accounts)

### Managing matches

Go to **Admin → Matches** to:

- Add knockout round matches manually once the bracket is known
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

**Note:** `simulate_phase round_of_32` and later knockout phases auto-build the bracket from the previous phase's results. In production, the admin creates knockout matches manually in the admin panel.

**Tip:** After simulating the group stage, run `simulate_phase round_of_32 --create-only` to create the R32 fixtures (so users can bet) before entering real results.

---

## URL reference

| URL | Description |
|---|---|
| `/` | Home / landing page |
| `/register/` | User registration (requires @threatfabric.com email) |
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
│   │       ├── load_data.py       # Load teams and group stage fixtures
│   │       └── simulate_phase.py  # Testing: simulate match results
│   ├── models.py                  # Data models
│   ├── views.py                   # Request handlers
│   ├── forms.py                   # Registration and prediction forms
│   ├── admin.py                   # Admin panel configuration
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
├── worldcup_sweepstake/           # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── manage.py
├── requirements.txt
└── README.md
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
    }
}
```

---

## Timezone

The app stores all times in UTC. The Django timezone is set to `Europe/Madrid` for display. To change it, update `TIME_ZONE` in `settings.py`.
