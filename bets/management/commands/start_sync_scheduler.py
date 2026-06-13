"""
Long-running scheduler that runs sync_results at timed intervals after each match.
Production only (refuses to start when DEBUG=True).

Sync schedule per match (relative to expected final whistle = kickoff + 90 min):
  +10 min, +30 min, +1 hour, +2 hours

Run as a systemd service: python manage.py start_sync_scheduler
"""
import datetime
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from bets.models import Match

MATCH_DURATION = datetime.timedelta(minutes=90)

SYNC_OFFSETS = [
    datetime.timedelta(minutes=10),
    datetime.timedelta(minutes=30),
    datetime.timedelta(hours=1),
    datetime.timedelta(hours=2),
]

# If the service was down and we missed a window, catch up if it was missed
# within this grace period.
CATCHUP_WINDOW = datetime.timedelta(minutes=5)

# When there are no upcoming matches, re-check after this interval.
IDLE_SLEEP_SECONDS = 3600


class Command(BaseCommand):
    help = (
        'Long-running scheduler: syncs results at fixed intervals after each match. '
        'Production only.'
    )

    def handle(self, *args, **options):
        if settings.DEBUG:
            self.stderr.write(self.style.ERROR(
                'Refusing to start: DEBUG=True. '
                'This command is for production only.'
            ))
            return

        self.stdout.write(self.style.SUCCESS('Sync scheduler started.'))

        while True:
            close_old_connections()
            now = timezone.now()
            next_run = self._next_sync_time(now)

            if next_run is None:
                # No unfinished matches in DB — run sync once to pick up fixtures
                # for the next round (API publishes them once the bracket is set).
                self.stdout.write('No upcoming syncs. Checking for new fixtures...')
                call_command('sync_results')
                self.stdout.write(
                    f'Sleeping {IDLE_SLEEP_SECONDS // 60} min before next check...'
                )
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            wait = (next_run - now).total_seconds()
            self.stdout.write(
                f'Next sync at {next_run.strftime("%Y-%m-%d %H:%M UTC")} '
                f'({wait / 60:.0f} min from now)'
            )
            if wait > 0:
                time.sleep(wait)

            self.stdout.write(
                f'Running sync_results at '
                f'{timezone.now().strftime("%Y-%m-%d %H:%M UTC")}'
            )
            call_command('sync_results')

    def _next_sync_time(self, now):
        """
        Return the nearest sync time that is either:
        - In the future, OR
        - Within the catchup grace window (missed while the service was down)
        """
        close_old_connections()
        catchup_from = now - CATCHUP_WINDOW

        # Only consider matches not yet marked finished in our DB.
        unfinished = Match.objects.filter(finished=False)

        candidates = []
        for match in unfinished:
            whistle = match.kickoff + MATCH_DURATION
            for offset in SYNC_OFFSETS:
                t = whistle + offset
                if t >= catchup_from:
                    candidates.append(t)

        if not candidates:
            return None

        # Return the earliest candidate; if it's already slightly in the past
        # (within the grace window) run immediately.
        earliest = min(candidates)
        return max(earliest, now)
