"""
Import ThreatFabric group-stage predictions from a Microsoft Forms CSV export.

Creates (idempotent — safe to re-run):
  - The "ThreatFabric" Sweepstake
  - One SweepstakeTeam per unique office team column
  - One Django User per participant (auto-generated password for new accounts)
  - One SweepstakeMembership per participant
  - One Bet per non-empty prediction (skips existing bets)

Usage:
    python manage.py import_tf_sweepstake path/to/predictions.csv
    python manage.py import_tf_sweepstake path/to/predictions.csv --dry-run
"""
import csv
import re
import secrets
import string

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from bets.models import (Bet, Match, NationalTeam, Sweepstake,
                         SweepstakeMembership, SweepstakeTeam)

SWEEPSTAKE_NAME = 'ThreatFabric'
SWEEPSTAKE_CODE = 'tf-wc-2026'

# CSV column / prediction team name → NationalTeam.name in DB
CSV_TO_DB_TEAM = {
    'Bosnia and Herzegovina': 'Bosnia & Herzegovina',
    'Curaçao':                'Curacao',
    'Türkiye':                'Turkey',
}

TEAM_COLORS = {
    'Data Science & ML':     '#10B981',
    'DevOps & Architecture': '#8B5CF6',
    'Executive':             '#EF4444',
    'HR & Finance':          '#3B82F6',
    'Intel':                 '#F59E0B',
    'Product Delivery':      '#6366F1',
    'Sales & Marketing':     '#EC4899',
}


def _random_password(length=14):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def _clean(text):
    """Strip regular and non-breaking whitespace."""
    return text.replace(' ', ' ').strip()


def _parse_match_header(header):
    """
    'Mexico vs South Africa (FINISHED)' → ('Mexico', 'South Africa')
    Returns (None, None) if it doesn't look like a match column.
    """
    clean = re.sub(r'\s*\(FINISHED\)\s*$', '', _clean(header))
    parts = clean.split(' vs ', 1)
    if len(parts) == 2:
        return _clean(parts[0]), _clean(parts[1])
    return None, None


def _lookup_match(home_raw, away_raw):
    """Resolve raw CSV team names to a Match object, or return None."""
    home_db = CSV_TO_DB_TEAM.get(home_raw, home_raw)
    away_db = CSV_TO_DB_TEAM.get(away_raw, away_raw)
    try:
        home = NationalTeam.objects.get(name=home_db)
        away = NationalTeam.objects.get(name=away_db)
        return Match.objects.get(home_team=home, away_team=away, phase='group_stage')
    except (NationalTeam.DoesNotExist, Match.DoesNotExist):
        return None


def _parse_prediction(value, home_raw, away_raw):
    """
    '🇲🇽 Mexico wins'    → 'home' or 'away' depending on position
    'Draw'               → 'draw'
    ''                   → None (no prediction, skip)
    """
    value = _clean(value)
    if not value:
        return None
    if value == 'Draw':
        return 'draw'
    if value.endswith(' wins'):
        if home_raw in value:
            return 'home'
        if away_raw in value:
            return 'away'
    return None


FIXED_COLS = {'ID', 'Start time', 'Completion time', 'Email', 'Name', 'Team'}


class Command(BaseCommand):
    help = 'Import ThreatFabric group-stage predictions from Microsoft Forms CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', help='Path to the exported CSV file')
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview what would happen without saving')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('--- DRY RUN — nothing will be saved ---\n'))

        # ── 1. Read CSV ───────────────────────────────────────────────────────
        with open(options['csv_file'], encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh, delimiter=';')
            rows = list(reader)

        if not rows:
            self.stderr.write('CSV is empty.')
            return

        # ── 2. Map match columns → Match objects ──────────────────────────────
        match_cols = {}   # original_col_key → (Match, home_raw, away_raw)
        skipped_cols = []

        for col in rows[0].keys():
            if col in FIXED_COLS:
                continue
            home_raw, away_raw = _parse_match_header(col)
            if not home_raw:
                continue
            match = _lookup_match(home_raw, away_raw)
            if match:
                match_cols[col] = (match, home_raw, away_raw)
            else:
                skipped_cols.append(f'{home_raw} vs {away_raw}')

        self.stdout.write(f'Match columns resolved: {len(match_cols)}')
        for s in skipped_cols:
            self.stdout.write(self.style.WARNING(f'  ⚠ No DB match for: {s}'))

        # ── 3. Deduplicate — keep latest submission per email ─────────────────
        by_email = {}
        for row in rows:
            email = row.get('Email', '').strip().lower()
            if not email:
                continue
            prev = by_email.get(email)
            if not prev or row['Completion time'] > prev['Completion time']:
                by_email[email] = row

        self.stdout.write(
            f'Participants: {len(by_email)} unique '
            f'({len(rows) - len(by_email)} duplicate(s) removed)\n'
        )

        # ── 4. Get/create Sweepstake ──────────────────────────────────────────
        if not dry_run:
            sweepstake, created = Sweepstake.objects.get_or_create(
                invite_code=SWEEPSTAKE_CODE,
                defaults={'name': SWEEPSTAKE_NAME},
            )
            verb = 'created' if created else 'already exists'
            self.stdout.write(f'Sweepstake "{sweepstake}" ({verb})')
        else:
            sweepstake = None

        # ── 5. Get/create SweepstakeTeams ─────────────────────────────────────
        office_teams = sorted({
            row.get('Team', '').strip()
            for row in by_email.values()
            if row.get('Team', '').strip()
        })
        team_objects = {}  # office_team_name → SweepstakeTeam

        for name in office_teams:
            color = TEAM_COLORS.get(name, '#6B7280')
            self.stdout.write(f'  Team: {name}  ({color})')
            if not dry_run:
                st, _ = SweepstakeTeam.objects.get_or_create(
                    name=name, sweepstake=sweepstake,
                    defaults={'color': color},
                )
                team_objects[name] = st

        self.stdout.write('')

        # ── 6. Process participants ────────────────────────────────────────────
        new_credentials = []

        with transaction.atomic():
            if dry_run:
                transaction.set_rollback(True)

            for email, row in sorted(by_email.items()):
                full_name = _clean(row.get('Name', ''))
                office_team_name = _clean(row.get('Team', ''))
                username = email.split('@')[0]

                # Find existing user by email first, then by username
                user = (
                    User.objects.filter(email__iexact=email).first()
                    or User.objects.filter(username__iexact=username).first()
                )

                if user:
                    self.stdout.write(f'  ~ {full_name} → existing user "{user.username}"')
                else:
                    password = _random_password()
                    parts = full_name.split(' ', 1)
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=parts[0],
                        last_name=parts[1] if len(parts) > 1 else '',
                    )
                    new_credentials.append((email, username, password))
                    self.stdout.write(
                        self.style.SUCCESS(f'  + {full_name} → new user "{username}"')
                    )

                if not dry_run:
                    # Membership
                    sweepstake_team = team_objects.get(office_team_name)
                    SweepstakeMembership.objects.get_or_create(
                        user=user, sweepstake=sweepstake,
                        defaults={'team': sweepstake_team},
                    )

                    # Bets
                    created_count = skipped_count = unparseable = 0
                    for col, (match, home_raw, away_raw) in match_cols.items():
                        value = row.get(col, '').strip()
                        if not value:
                            continue
                        predicted_winner = _parse_prediction(value, home_raw, away_raw)
                        if predicted_winner is None:
                            unparseable += 1
                            self.stdout.write(
                                f'    ⚠ Cannot parse: "{value}" '
                                f'({home_raw} vs {away_raw})'
                            )
                            continue

                        bet, bet_created = Bet.objects.get_or_create(
                            user=user, match=match,
                            defaults={'predicted_winner': predicted_winner},
                        )
                        if bet_created:
                            if match.finished:
                                bet.points_earned = match.calculate_bet_points(bet)
                                bet.save(update_fields=['points_earned'])
                            created_count += 1
                        else:
                            skipped_count += 1

                    self.stdout.write(
                        f'    → {created_count} bets created, '
                        f'{skipped_count} skipped (already exist), '
                        f'{unparseable} unparseable'
                    )

        # ── 7. Print new credentials ──────────────────────────────────────────
        if new_credentials and not dry_run:
            self.stdout.write('\n' + '=' * 64)
            self.stdout.write('NEW USER CREDENTIALS — share securely with each participant')
            self.stdout.write('=' * 64)
            for cred_email, uname, pw in new_credentials:
                self.stdout.write(f'  {cred_email}')
                self.stdout.write(f'    username: {uname}  |  password: {pw}')
            self.stdout.write('=' * 64)
            self.stdout.write(
                'Users can change their password after first login '
                '(not yet implemented — consider adding this).'
            )
