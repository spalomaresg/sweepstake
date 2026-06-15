import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from bets.models import SweepstakeTeam, Sweepstake

TEAMS_CSV_PATH = os.path.join(settings.BASE_DIR, 'teams.csv')


class Command(BaseCommand):
    help = 'Load sweepstake teams from teams.csv (columns: team, color) into a specific sweepstake'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sweepstake',
            required=True,
            help='Sweepstake invite code or name to load teams into',
        )

    def handle(self, *args, **options):
        sweepstake_ref = options['sweepstake']
        try:
            sweepstake = Sweepstake.objects.get(invite_code__iexact=sweepstake_ref)
        except Sweepstake.DoesNotExist:
            try:
                sweepstake = Sweepstake.objects.get(name__iexact=sweepstake_ref)
            except Sweepstake.DoesNotExist:
                raise CommandError(
                    f'No sweepstake found with invite code or name: {sweepstake_ref}\n'
                    'Create one in the Django admin (/admin/) first.'
                )

        if not os.path.exists(TEAMS_CSV_PATH):
            raise CommandError(f'teams.csv not found at {TEAMS_CSV_PATH}')

        created = updated = 0
        with open(TEAMS_CSV_PATH, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('team', '').strip()
                color = row.get('color', '').strip() or '#3B82F6'
                if not name:
                    continue
                _, is_new = SweepstakeTeam.objects.update_or_create(
                    name=name,
                    sweepstake=sweepstake,
                    defaults={'color': color},
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {updated} updated in "{sweepstake.name}".'
        ))
