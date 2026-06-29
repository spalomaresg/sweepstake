"""
Sync finished match results AND create upcoming fixtures from api-sports.io (API-Football v3).

Sign up for a free key at https://dashboard.api-football.com/register (100 req/day free).
Set API_FOOTBALL_KEY in your .env file.

Run: python manage.py sync_results
Run (dry run): python manage.py sync_results --dry-run
"""
import datetime
import json
import urllib.request
import urllib.error

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from bets.models import Match, NationalTeam

API_BASE = 'https://v3.football.api-sports.io'
WC_LEAGUE_ID = 1
WC_SEASON = 2026

# api-sports.io round string → our phase key
ROUND_MAP = {
    'Round of 32':     'round_of_32',
    'Round of 16':     'round_of_16',
    'Quarter-finals':  'quarterfinals',
    'Semi-finals':     'semifinals',
    '3rd Place Final': 'third_place',
    'Final':           'final',
}

# API team names that differ from our NationalTeam.name values
API_NAME_MAP = {
    'Korea Republic':                   'South Korea',
    'United States':                    'USA',
    "Côte d'Ivoire":                    'Ivory Coast',
    'Bosnia and Herzegovina':           'Bosnia & Herzegovina',
    'Bosnia-Herzegovina':               'Bosnia & Herzegovina',
    'Curaçao':                          'Curacao',
    'Congo DR':                         'DR Congo',
    'Congo, DR':                        'DR Congo',
    'Democratic Republic of the Congo': 'DR Congo',
}


def _round_to_phase(round_str):
    if round_str.startswith('Group Stage'):
        return 'group_stage'
    return ROUND_MAP.get(round_str)


class Command(BaseCommand):
    help = 'Sync finished results and create upcoming fixtures from api-sports.io'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview what would change without saving anything',
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, 'API_FOOTBALL_KEY', '')
        if not api_key:
            self.stderr.write(self.style.ERROR(
                'API_FOOTBALL_KEY is not set. '
                'Register at https://dashboard.api-football.com/register and add it to .env'
            ))
            return

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('--- DRY RUN — nothing will be saved ---'))

        self.stdout.write(f'Fetching WC {WC_SEASON} fixtures from api-sports.io...')
        api_matches = self._fetch_all_matches(api_key)
        if api_matches is None:
            return

        self.stdout.write(f'Received {len(api_matches)} matches from API\n')

        team_by_code = {t.code: t for t in NationalTeam.objects.all()}
        team_by_name = {t.name: t for t in NationalTeam.objects.all()}

        results_updated = results_done = results_missed = 0
        fixtures_created = fixtures_exist = 0

        for api_match in api_matches:
            round_str = api_match['league']['round']
            phase = _round_to_phase(round_str)
            if not phase:
                continue

            kickoff = datetime.datetime.fromisoformat(api_match['fixture']['date'])
            status = api_match['fixture']['status']['short']

            # FT = full time, AET = after extra time, PEN = after penalties
            if status in ('FT', 'AET', 'PEN'):
                outcome = self._sync_result(api_match, phase, kickoff, dry_run)
                if outcome == 'updated':    results_updated += 1
                elif outcome == 'done':     results_done += 1
                else:                       results_missed += 1

            elif status in ('NS', 'TBD') and phase != 'group_stage':
                outcome = self._create_fixture(
                    api_match, phase, kickoff, dry_run, team_by_code, team_by_name
                )
                if outcome == 'created':    fixtures_created += 1
                elif outcome == 'exists':   fixtures_exist += 1

        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{prefix}Results:  {results_updated} updated · '
            f'{results_done} already finished · {results_missed} not found in DB'
        ))
        if fixtures_created or fixtures_exist:
            self.stdout.write(self.style.SUCCESS(
                f'{prefix}Fixtures: {fixtures_created} created · '
                f'{fixtures_exist} already exist'
            ))

    # ── API fetching ──────────────────────────────────────────────────────────

    def _fetch_all_matches(self, api_key):
        matches = []
        page = 1
        while True:
            url = f'{API_BASE}/fixtures?league={WC_LEAGUE_ID}&season={WC_SEASON}&page={page}'
            req = urllib.request.Request(url, headers={'x-apisports-key': api_key})
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read())
            except urllib.error.HTTPError as e:
                self.stderr.write(self.style.ERROR(f'API returned {e.code}: {e.reason}'))
                return None
            except urllib.error.URLError as e:
                self.stderr.write(self.style.ERROR(f'Network error: {e.reason}'))
                return None

            matches.extend(data.get('response', []))

            paging = data.get('paging', {})
            if paging.get('current', 1) >= paging.get('total', 1):
                break
            page += 1

        return matches

    # ── Result sync ───────────────────────────────────────────────────────────

    def _sync_result(self, api_match, phase, kickoff, dry_run):
        try:
            match = Match.objects.get(kickoff=kickoff)
        except Match.DoesNotExist:
            home = api_match['teams']['home']['name']
            away = api_match['teams']['away']['name']
            self.stdout.write(f'  ⚠  Not in DB: {kickoff}  {home} vs {away}')
            return 'missed'

        if match.finished:
            return 'done'

        # Use fulltime score (90 min), not including ET/penalties
        home_goals = api_match['score']['fulltime']['home']
        away_goals = api_match['score']['fulltime']['away']

        if api_match['teams']['home']['winner']:
            api_winner = 'HOME_TEAM'
        elif api_match['teams']['away']['winner']:
            api_winner = 'AWAY_TEAM'
        else:
            api_winner = 'DRAW'

        if dry_run:
            self.stdout.write(f'  ~ {match}  →  {home_goals}–{away_goals}  ({api_winner})')
            return 'updated'

        match.home_goals = home_goals
        match.away_goals = away_goals
        match.finished = True

        if match.is_knockout:
            if api_winner == 'HOME_TEAM':
                match.knockout_winner = 'home'
            elif api_winner == 'AWAY_TEAM':
                match.knockout_winner = 'away'

        match.save()

        bets = list(match.bets.all())
        for bet in bets:
            bet.points_earned = match.calculate_bet_points(bet)
        if bets:
            with transaction.atomic():
                for bet in bets:
                    bet.save(update_fields=['points_earned'])

        self.stdout.write(self.style.SUCCESS(f'  ✓  {match}  →  {home_goals}–{away_goals}'))
        return 'updated'

    # ── Fixture creation ──────────────────────────────────────────────────────

    def _create_fixture(self, api_match, phase, kickoff, dry_run, team_by_code, team_by_name):
        home_data = api_match['teams']['home']
        away_data = api_match['teams']['away']

        # Skip placeholder entries where the bracket isn't set yet
        if not home_data.get('id') or not away_data.get('id'):
            return 'skip'

        home = self._resolve_team(home_data, team_by_code, team_by_name)
        away = self._resolve_team(away_data, team_by_code, team_by_name)

        if not home:
            self.stdout.write(f'  ⚠  Unknown home team: {home_data.get("name")} ({home_data.get("code")})')
            return 'skip'
        if not away:
            self.stdout.write(f'  ⚠  Unknown away team: {away_data.get("name")} ({away_data.get("code")})')
            return 'skip'

        if Match.objects.filter(home_team=home, away_team=away, phase=phase).exists():
            return 'exists'

        if dry_run:
            self.stdout.write(
                f'  ~ Would create: {home} vs {away}  '
                f'[{kickoff.strftime("%Y-%m-%d %H:%M")} UTC]  ({phase})'
            )
            return 'created'

        Match.objects.create(home_team=home, away_team=away, phase=phase, kickoff=kickoff)
        self.stdout.write(self.style.SUCCESS(
            f'  ✓  New fixture: {home} vs {away}  '
            f'[{kickoff.strftime("%Y-%m-%d %H:%M")} UTC]  ({phase})'
        ))
        return 'created'

    def _resolve_team(self, api_team, team_by_code, team_by_name):
        # 3-letter code is the most reliable identifier
        code = api_team.get('code', '')
        if code and code in team_by_code:
            return team_by_code[code]
        # Fall back to name matching with normalisation
        name = api_team.get('name', '')
        normalized = API_NAME_MAP.get(name, name)
        return team_by_name.get(normalized)
