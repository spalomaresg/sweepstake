# Sweepstake — Project Context

## What this is

Django + SQLite sweepstake app for FIFA World Cup 2026. Users predict match results, earn points, and compete on a leaderboard individually and by sweepstake team.

- **Stack:** Django 4.2, SQLite, Whitenoise, gunicorn, nginx, Tailwind CSS (CDN)
- **Deployment:** miniPC at home running Proxmox; VM inside Proxmox hosts the app; exposed via FritzBox 5590 port forwarding + DuckDNS
- **Languages:** English and Spanish (controlled via `LANGUAGE` in `.env`)
- **Auth:** invite-only via `valid_emails.csv` (email + invite code per user)
- **API keys:** hardcoded in `worldcup_sweepstake/settings.py`, not in `.env`

## Results API

**Active:** football-data.org v4
- Key: `FOOTBALL_DATA_API_KEY` in `settings.py`
- Competition code: `WC`, endpoint: `/competitions/WC/matches`, auth header: `X-Auth-Token`

**Do not switch to api-sports.io** — their free tier only covers seasons up to 2024. WC 2026 is behind a paid plan. The adapter code was written and tested but reverted (find it in git history if ever needed with a paid plan).

## Tournament phases

In order: `group_stage` → `round_of_32` → `round_of_16` → `quarterfinals` → `semifinals` → `third_place` / `final`

- The tournament **does** have a round_of_32 (32 teams: top 2 from each of 12 groups + best 8 third-place teams)
- `third_place` and `final` are concurrent and treated as a pair

## Scoring

| Phase | Correct winner | Exact score |
|---|---|---|
| Group stage | 1 pt | — |
| Round of 32 / Round of 16 | 1 pt | +2 pts |
| Quarters / Semis / Third place | 2 pts | +4 pts |
| Final | 5 pts | +10 pts |

- Exact score is based on 90-min result (or ET score if ET was played) — **not** including penalty goals
- Penalty goals stored separately: `Match.penalty_home_goals` / `Match.penalty_away_goals`
- `knockout_winner` field ('home'/'away') set only when match went to penalties (tied score after ET)
- Points are recalculated automatically via a `post_save` signal on `Match` whenever `finished=True`

## Betting rules

- Users can bet on **any match in any phase** as long as the match hasn't kicked off yet (`now < match.kickoff`)
- There is no phase-level restriction — `get_bettable_phases()` was removed and no longer exists
- `save_prediction_ajax` only checks kickoff time; nothing else gates a bet
- Per-phase `is_bettable` in the view context means "this phase has at least one unstarted match" — used only for the 🔒 Locked banner in the UI

## Per-phase exclusion from team stats

Users can be excluded from team stats for specific phases (e.g. someone who only participated in the group stage) via `MembershipPhaseExclusion` model.

- Model: `MembershipPhaseExclusion(membership FK, phase CharField)`
- Admin: go to **Sweepstake Memberships**, open a specific membership, add phase exclusions inline
- Effect: `SweepstakeTeam._members_for_phase(phase_key)` excludes those users when computing phase averages
- `_active_members()` still returns everyone (used only for the Members count column)
- The leaderboard "Avg Total" is computed as sum of per-phase averages (not total/all_members), so it stays consistent with the displayed columns even when exclusions differ by phase

## Leaderboard features

**Individual table — phase point display:**
- `—` (dim) = player placed no bets in that phase
- `0` (slightly muted) = player bet but scored nothing
- `N` (bright) = points earned
- Implemented via `_points_by_phase_for_user` returning `None` for no-bet phases, and `pts_display` / `is_none` filters in `bets/templatetags/bet_extras.py`

**Teams table — bump/ranking chart:**
- Canvas-based bump chart below the teams table showing team rank positions across completed phases
- Data computed in the `leaderboard` view: cumulative avg pts → rank at each phase → serialized as `bump_chart_data` JSON per sweepstake
- Rendered in `templates/bets/leaderboard.html` via inline Canvas JS (`drawBump`, `initBump`, `redrawBump`)
- Animates left-to-right on first tab visit; redraws on resize; hover tooltips show team/phase/rank/pts
- Only appears when `ordered_phases` is non-empty (at least one finished match exists)

**Combined Final & Third Place tab:**
- `third_place` and `final` are merged into a single "Final & Third Place" tab in My Predictions
- Each match row shows its phase label and per-match scoring (different points for each)
- `is_combined: True` flag in `phases_data`; per-row `phase_label`, `points_winner`, `points_exact`
- Phase-level `third_place_pts` and `final_pts` tuples for the scoring banner

## My Predictions page

**Default tab:** Opens on the oldest phase that isn't fully complete (i.e. where the tournament currently is). Falls back to the last phase if all are done. Phases with no matches are skipped entirely — no "bracket being assembled" tab.

**Prediction column layout** — both locked and unlocked rows use the same 5-element flex structure so columns align perfectly:

- Unlocked: `Button(flex-1) | input(w-10 md:w-12) | span–(w-4) | input(w-10 md:w-12) | Button(flex-1)`
- Locked: `Button(flex-1) | span(w-10 md:w-12) | span–(w-4) | span(w-10 md:w-12) | Button(flex-1)`

Group stage (desktop): home/away buttons use `md:flex-1`; draw button uses `md:flex-none md:w-20`.

When a match kicks off mid-session, `lockMatchUI()` in the page JS replaces the inputs with spans of identical classes — same structure as server-rendered locked rows.

## Key management commands

```bash
# Sync results from football-data.org
python manage.py sync_results
python manage.py sync_results --dry-run      # preview without saving

# Create fixtures for a knockout phase from actual results
python manage.py create_fixture round_of_32
python manage.py create_fixture round_of_16
python manage.py create_fixture quarterfinals
python manage.py create_fixture semifinals
python manage.py create_fixture third_place
python manage.py create_fixture final

# Long-running scheduler (run as systemd service on the server, not locally)
python manage.py start_sync_scheduler

# Testing only
python manage.py simulate_phase <phase>

# Initial data load
python manage.py load_data    # 48 national teams + 72 group stage matches
python manage.py load_teams   # sweepstake teams from teams.csv
```

## Important constraints

- **Do not run commands on the remote server directly** — always provide commands for the user to run themselves on the server
- `start_sync_scheduler` is production-only (DEBUG=False) and runs as a systemd service on the server
- No hot-reload in production — after any Python file change, restart the service (`sudo systemctl restart django-sweepstake` or whatever the service is named)
- Template changes take effect immediately without a restart (Django renders them at request time)
