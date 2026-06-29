"""
Create match fixtures for a knockout phase based on actual results.

For round_of_16: resolves teams from actual group standings using the official bracket.
For later rounds:  pairs up winners from the previous finished phase.

Usage:
  python manage.py create_fixture round_of_16
  python manage.py create_fixture quarterfinals
  python manage.py create_fixture semifinals
  python manage.py create_fixture third_place
  python manage.py create_fixture final
"""
from django.core.management.base import BaseCommand, CommandError

from bets.models import PHASE_CHOICES


CREATABLE_PHASES = [p[0] for p in PHASE_CHOICES if p[0] != 'group_stage']


class Command(BaseCommand):
    help = 'Create match fixtures for a knockout phase based on actual results'

    def add_arguments(self, parser):
        parser.add_argument(
            'phase', type=str,
            help=f'Phase to create fixtures for. One of: {", ".join(CREATABLE_PHASES)}',
        )

    def handle(self, *args, **options):
        from bets.management.commands.simulate_phase import Command as SimCmd

        phase = options['phase']
        if phase not in CREATABLE_PHASES:
            raise CommandError(
                f"Unknown phase '{phase}'. Choose one of: {', '.join(CREATABLE_PHASES)}"
            )

        cmd = SimCmd()
        cmd.stdout = self.stdout
        cmd.stderr = self.stderr
        cmd.style = self.style
        cmd._create_matches_only(phase)
