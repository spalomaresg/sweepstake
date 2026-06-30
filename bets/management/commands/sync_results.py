"""
Sync finished match results AND create upcoming fixtures from football-data.org.

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

API_BASE = 'https://api.football-data.org/v4'
DEFAULT_COMPETITION = 'WC'

# football-data.org stage value → our phase key
STAGE_MAP = {
    'GROUP_STAGE':    'group_stage',
    'LAST_32':        'round_of_32',
    'LAST_16':        'round_of_16',
    'QUARTER_FINALS': 'quarterfinals',
    'SEMI_FINALS':    'semifinals',
    'THIRD_PLACE':    'third_place',
    'FINAL':          'final',
}

# API team names that differ from our NationalTeam.name values
API_NAME_MAP = {
    'Korea Republic':                   'South Korea',
    'United States':                    'USA',
    "Côte d'Ivoire":                    'Ivory Coast',
    'Bosnia-Herzegovina':               'Bosnia & Herzegovina',
    'Bosnia and Herzegovina':           'Bosnia & Herzegovina',
    'Curaçao':                          'Curacao',
    'Congo DR':                         'DR Congo',
    'Congo, DR':                        'DR Congo',
    'Democratic Republic of the Congo': 'DR Congo',
}


class Command(BaseCommand):
    help = 'Sync finished results and create upcoming fixtures from football-data.org'

    def add_arguments(self, parser):
        parser.add_argument(
            '--competition', default=DEFAULT_COMPETITION,
            help=f'Competition code (default: {DEFAULT_COMPETITION})',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview what would change without saving anything',
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, 'FOOTBALL_DATA_API_KEY', '')
        if not api_key:
            self.stderr.write(self.style.ERROR('FOOTBALL_DATA_API_KEY is not set in settings.py'))
            return

        competition = options['competition']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('--- DRY RUN — nothing will be saved ---'))

        self.stdout.write(f'Fetching matches for {competition}...')
        url = f'{API_BASE}/competitions/{competition}/matches'
        req = urllib.request.Request(url, headers={'X-Auth-Token': api_key})

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            self.stderr.write(self.style.ERROR(f'API returned {e.code}: {e.reason}'))
            return
        except urllib.error.URLError as e:
            self.stderr.write(self.style.ERROR(f'Network error: {e.reason}'))
            return

        api_matches = data.get('matches', [])
        self.stdout.write(f'Received {len(api_matches)} matches from API\n')

        team_by_tla  = {t.code: t for t in NationalTeam.objects.all()}
        team_by_name = {t.name: t for t in NationalTeam.objects.all()}

        results_updated = results_done = results_missed = 0
        fixtures_created = fixtures_exist = 0

        for api_match in api_matches:
            stage = api_match.get('stage', '')
            phase = STAGE_MAP.get(stage)
            if not phase:
                continue

            kickoff = datetime.datetime.fromisoformat(
                api_match['utcDate'].replace('Z', '+00:00')
            )
            status = api_match['status']

            if status == 'FINISHED':
                outcome = self._sync_result(api_match, phase, kickoff, dry_run, team_by_tla, team_by_name)
                if outcome == 'updated':   results_updated += 1
                elif outcome == 'done':    results_done += 1
                else:                      results_missed += 1

            elif status in ('SCHEDULED', 'TIMED') and phase != 'group_stage':
                outcome = self._create_fixture(
                    api_match, phase, kickoff, dry_run, team_by_tla, team_by_name
                )
                if outcome == 'created':   fixtures_created += 1
                elif outcome == 'exists':  fixtures_exist += 1

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

    # ── Result sync ───────────────────────────────────────────────────────────

    def _sync_result(self, api_match, phase, kickoff, dry_run, team_by_tla, team_by_name):
        home = self._resolve_team(api_match['homeTeam'], team_by_tla, team_by_name)
        away = self._resolve_team(api_match['awayTeam'], team_by_tla, team_by_name)
        try:
            match = Match.objects.get(kickoff=kickoff, home_team=home, away_team=away)
        except Match.DoesNotExist:
            self.stdout.write(
                f'  ⚠  Not in DB: {kickoff}  '
                f'{api_match["homeTeam"]["name"]} vs {api_match["awayTeam"]["name"]}'
            )
            return 'missed'

        if match.finished:
            return 'done'

        score = api_match['score']
        api_winner = score['winner']  # 'HOME_TEAM' | 'AWAY_TEAM' | 'DRAW'

        # Use extraTime score when ET was played (cumulative, includes regular time goals).
        # This ensures home_goals/away_goals reflect the actual pre-penalty score.
        extra = score.get('extraTime') or {}
        if extra.get('home') is not None:
            home_goals = extra['home']
            away_goals = extra['away']
        else:
            home_goals = score['fullTime']['home']
            away_goals = score['fullTime']['away']

        # Penalty shootout goals — stored separately for display
        pens = score.get('penalties') or {}
        penalty_home = pens.get('home')
        penalty_away = pens.get('away')

        if dry_run:
            pen_str = f'  pens {penalty_home}–{penalty_away}' if penalty_home is not None else ''
            self.stdout.write(
                f'  ~ {match}  →  {home_goals}–{away_goals}{pen_str}  ({api_winner})'
            )
            return 'updated'

        match.home_goals = home_goals
        match.away_goals = away_goals
        match.penalty_home_goals = penalty_home
        match.penalty_away_goals = penalty_away
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

        pen_str = f'  pens {penalty_home}–{penalty_away}' if penalty_home is not None else ''
        self.stdout.write(
            self.style.SUCCESS(f'  ✓  {match}  →  {home_goals}–{away_goals}{pen_str}')
        )
        return 'updated'

    # ── Fixture creation ──────────────────────────────────────────────────────

    def _create_fixture(self, api_match, phase, kickoff, dry_run, team_by_tla, team_by_name):
        home_data = api_match.get('homeTeam', {})
        away_data = api_match.get('awayTeam', {})

        if not home_data.get('id') or not away_data.get('id'):
            return 'skip'

        home = self._resolve_team(home_data, team_by_tla, team_by_name)
        away = self._resolve_team(away_data, team_by_tla, team_by_name)

        if not home:
            self.stdout.write(
                f'  ⚠  Unknown home team: {home_data.get("name")} ({home_data.get("tla")})'
            )
            return 'skip'
        if not away:
            self.stdout.write(
                f'  ⚠  Unknown away team: {away_data.get("name")} ({away_data.get("tla")})'
            )
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

    def _resolve_team(self, api_team, team_by_tla, team_by_name):
        tla = api_team.get('tla', '')
        if tla and tla in team_by_tla:
            return team_by_tla[tla]
        name = api_team.get('name', '')
        normalized = API_NAME_MAP.get(name, name)
        return team_by_name.get(normalized)
