"""
Simulate results for a specific phase to test scoring and bracket progression.

Usage:
  python manage.py simulate_phase group_stage
  python manage.py simulate_phase round_of_32
  python manage.py simulate_phase round_of_16
  python manage.py simulate_phase quarterfinals
  python manage.py simulate_phase semifinals
  python manage.py simulate_phase third_place
  python manage.py simulate_phase final
  python manage.py simulate_phase all              # end-to-end simulation
  python manage.py simulate_phase group_stage --reset   # undo results
  python manage.py simulate_phase --seed 42        # reproducible results
"""
import random
import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from bets.models import (
    Match, Bet, NationalTeam, PHASE_CHOICES, PHASE_ORDER,
    get_group_standings,
)

# ── Official FIFA WC 2026 Round of 32 bracket ─────────────────────────────
# Source: ESPN / NBC Sports / Sky Sports confirmed schedule
# Format: (match_no, home_slot, away_slot, date_utc, venue)
# Slots: "X1"=winner group X, "X2"=runner-up group X, "X3"=best 3rd from X
# 3rd-place slots are resolved at runtime based on actual standings.

ROUND_OF_32 = [
    # June 29
    (76, "C1",  "F2",  "2026-06-29 17:00", "Houston"),
    (74, "E1",  "3rd_ABCDF", "2026-06-29 20:30", "Boston"),
    (75, "F1",  "C2",  "2026-06-30 01:00", "Monterrey"),
    # June 30
    (78, "E2",  "I2",  "2026-06-30 17:00", "Dallas"),
    (77, "I1",  "3rd_CDFGH", "2026-06-30 21:00", "New York"),
    (79, "A1",  "3rd_CEFHI", "2026-07-01 01:00", "Mexico City"),
    # July 1
    (80, "L1",  "3rd_EHIJK", "2026-07-01 16:00", "Atlanta"),
    (82, "G1",  "3rd_AEHIJ", "2026-07-01 20:00", "Seattle"),
    (81, "D1",  "3rd_BEFIJ", "2026-07-02 00:00", "San Francisco"),
    # July 2
    (84, "H1",  "J2",  "2026-07-02 17:00", "Los Angeles"),
    (83, "K2",  "L2",  "2026-07-03 00:00", "Toronto"),
    (85, "B1",  "3rd_EFGIJ", "2026-07-03 08:00", "Vancouver"),
    # July 3
    (88, "D2",  "G2",  "2026-07-03 19:00", "Dallas"),
    (86, "J1",  "H2",  "2026-07-03 23:00", "Miami"),
    (87, "K1",  "3rd_DEIJL", "2026-07-04 02:30", "Kansas City"),
    # July 4
    (73, "A2",  "B2",  "2026-07-04 17:00", "Los Angeles"),
]

# Round of 16 official dates (teams TBD based on R32 results)
ROUND_OF_16_DATES = [
    "2026-07-04 17:00",
    "2026-07-04 21:00",
    "2026-07-05 20:00",
    "2026-07-06 00:00",
    "2026-07-06 19:00",
    "2026-07-06 23:00",
    "2026-07-07 16:00",
    "2026-07-07 20:00",
]

QUARTERFINAL_DATES = [
    "2026-07-09 20:00",
    "2026-07-10 00:00",
    "2026-07-10 20:00",
    "2026-07-11 00:00",
]

SEMIFINAL_DATES = [
    "2026-07-14 23:00",
    "2026-07-15 23:00",
]

THIRD_PLACE_DATE  = "2026-07-18 19:00"
FINAL_DATE        = "2026-07-19 19:00"


def utc(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=datetime.timezone.utc)


def random_score(is_knockout=False):
    while True:
        h = random.randint(0, 4)
        a = random.randint(0, 4)
        if is_knockout and h == 0 and a == 0:
            continue
        return h, a


def random_ko_winner(h, a):
    if h > a: return 'home'
    if a > h: return 'away'
    return random.choice(['home', 'away'])


def get_slot(group, position):
    """Return team at position (1=winner, 2=runner-up, 3=third) in a group."""
    standings = get_group_standings(group)
    if len(standings) < position:
        return None
    return standings[position - 1].team


def resolve_best_third(groups_str):
    """
    Resolve the best third-place team from the given group candidates.
    groups_str is like 'ABCDF' — pick the best 3rd from those groups by pts/gd/gf.
    """
    candidates = []
    for g in groups_str:
        standings = get_group_standings(g)
        if len(standings) >= 3:
            candidates.append(standings[2])
    if not candidates:
        return None
    best = max(candidates, key=lambda s: (s.points, s.gd, s.gf))
    return best.team


def resolve_slot(slot):
    """Resolve a slot string like 'A1', 'C2', '3rd_ABCDF' to a NationalTeam."""
    if slot.startswith('3rd_'):
        groups = slot[4:]
        return resolve_best_third(groups)
    group = slot[0]
    pos = int(slot[1])
    return get_slot(group, pos)


class Command(BaseCommand):
    help = 'Simulate match results for a phase to test scoring and bracket progression.'

    def add_arguments(self, parser):
        parser.add_argument('phase', type=str, help='Phase key or "all"')
        parser.add_argument('--reset', action='store_true',
                            help='Clear results for the given phase')
        parser.add_argument('--create-only', action='store_true',
                            help='Only create matches (do not simulate results)')
        parser.add_argument('--seed', type=int, default=None,
                            help='Random seed for reproducibility')

    def handle(self, *args, **options):
        phase_arg = options['phase']
        do_reset = options['reset']
        seed = options['seed']

        valid = [p[0] for p in PHASE_CHOICES] + ['all']
        if phase_arg not in valid:
            raise CommandError(f"Unknown phase '{phase_arg}'. Choose: {', '.join(valid)}")

        if seed is not None:
            random.seed(seed)
            self.stdout.write(f"Seed: {seed}")

        create_only = options['create_only']
        phases = PHASE_ORDER if phase_arg == 'all' else [phase_arg]
        for p in phases:
            if do_reset:
                self._reset_phase(p)
            elif create_only:
                self._create_matches_only(p)
            else:
                self._simulate_phase(p)

    # ── Reset ──────────────────────────────────────────────────────────────

    def _reset_phase(self, phase_key):
        qs = Match.objects.filter(phase=phase_key)
        if not qs.exists():
            self.stdout.write(f"  No matches in {phase_key}")
            return
        for m in qs:
            m.home_goals = None; m.away_goals = None
            m.knockout_winner = None; m.finished = False; m.save()
            for bet in m.bets.all():
                bet.points_earned = 0; bet.save()
        self.stdout.write(self.style.WARNING(f"✗ Reset {qs.count()} matches in {phase_key}"))

    # ── Create only ────────────────────────────────────────────────────────

    def _create_matches_only(self, phase_key):
        """Create matches for a phase without simulating results."""
        if phase_key == 'round_of_32':
            self._create_round_of_32()
        elif phase_key in ('round_of_16', 'quarterfinals', 'semifinals'):
            self._create_from_winners(phase_key)
        elif phase_key == 'third_place':
            self._create_third_place()
        elif phase_key == 'final':
            self._create_final()
        else:
            self.stdout.write(f"  No match creation needed for {phase_key}")

    # ── Simulate ───────────────────────────────────────────────────────────

    def _simulate_phase(self, phase_key):
        is_ko = phase_key != 'group_stage'

        if phase_key == 'round_of_32':
            self._create_round_of_32()
        elif phase_key in ('round_of_16', 'quarterfinals', 'semifinals'):
            self._create_from_winners(phase_key)
        elif phase_key == 'third_place':
            self._create_third_place()
        elif phase_key == 'final':
            self._create_final()

        matches = Match.objects.filter(phase=phase_key).select_related('home_team','away_team')
        if not matches.exists():
            self.stdout.write(self.style.WARNING(f"  No matches for {phase_key} — skipping."))
            return

        label = dict(PHASE_CHOICES)[phase_key]
        self.stdout.write(f"\n{'='*60}\n  {label.upper()}\n{'='*60}")

        for m in matches:
            h, a = random_score(is_ko)
            kw = random_ko_winner(h, a) if is_ko else None
            m.home_goals = h; m.away_goals = a
            m.knockout_winner = kw; m.finished = True; m.save()
            for bet in m.bets.all():
                bet.points_earned = m.calculate_bet_points(bet); bet.save()
            adv = ""
            if kw and h == a:
                adv = f"  (pens → {m.home_team.name if kw=='home' else m.away_team.name})"
            self.stdout.write(
                f"  {m.home_team.flag} {m.home_team.name:<20} {h} – {a}  "
                f"{m.away_team.flag} {m.away_team.name:<20}{adv}"
            )

        if phase_key == 'group_stage':
            self._print_standings()

        self.stdout.write(self.style.SUCCESS(f"\n✓ {matches.count()} matches simulated\n"))

    # ── Bracket builders ───────────────────────────────────────────────────

    def _create_round_of_32(self):
        if Match.objects.filter(phase='round_of_32').exists():
            return
        self.stdout.write("\n  Building Round of 32 from official bracket...")
        created = 0
        for match_no, home_slot, away_slot, date_str, venue in ROUND_OF_32:
            home = resolve_slot(home_slot)
            away = resolve_slot(away_slot)
            if not home or not away:
                self.stdout.write(self.style.WARNING(
                    f"    Cannot resolve {home_slot} vs {away_slot} — skipping"))
                continue
            Match.objects.create(
                home_team=home, away_team=away,
                phase='round_of_32', kickoff=utc(date_str)
            )
            self.stdout.write(f"    M{match_no}: {home} vs {away}  [{date_str} UTC]")
            created += 1
        self.stdout.write(f"  Created {created} Round of 32 matches.")

    def _create_from_winners(self, phase_key):
        if Match.objects.filter(phase=phase_key).exists():
            return
        prev = {'round_of_16': 'round_of_32', 'quarterfinals': 'round_of_16',
                'semifinals': 'quarterfinals'}[phase_key]
        prev_matches = Match.objects.filter(phase=prev, finished=True).order_by('kickoff')
        if not prev_matches.exists():
            self.stdout.write(self.style.WARNING(f"  No finished {prev} matches."))
            return
        winners = [m.home_team if m.winner == 'home' else m.away_team for m in prev_matches]
        dates = {'round_of_16': ROUND_OF_16_DATES,
                 'quarterfinals': QUARTERFINAL_DATES,
                 'semifinals': SEMIFINAL_DATES}[phase_key]
        created = 0
        for i in range(0, len(winners) - 1, 2):
            d = dates[i // 2] if i // 2 < len(dates) else dates[-1]
            Match.objects.create(
                home_team=winners[i], away_team=winners[i+1],
                phase=phase_key, kickoff=utc(d)
            )
            self.stdout.write(f"    {winners[i]} vs {winners[i+1]}  [{d} UTC]")
            created += 1
        self.stdout.write(f"  Created {created} {phase_key} matches.")

    def _create_third_place(self):
        if Match.objects.filter(phase='third_place').exists():
            return
        semis = Match.objects.filter(phase='semifinals', finished=True).order_by('kickoff')
        losers = []
        for m in semis:
            losers.append(m.away_team if m.winner == 'home' else m.home_team)
        if len(losers) < 2:
            self.stdout.write(self.style.WARNING("  Need 2 finished semis for 3rd place."))
            return
        Match.objects.create(home_team=losers[0], away_team=losers[1],
                              phase='third_place', kickoff=utc(THIRD_PLACE_DATE))
        self.stdout.write(f"  3rd place: {losers[0]} vs {losers[1]}")

    def _create_final(self):
        if Match.objects.filter(phase='final').exists():
            return
        semis = Match.objects.filter(phase='semifinals', finished=True).order_by('kickoff')
        winners = [m.home_team if m.winner == 'home' else m.away_team for m in semis]
        if len(winners) < 2:
            self.stdout.write(self.style.WARNING("  Need 2 finished semis for final."))
            return
        Match.objects.create(home_team=winners[0], away_team=winners[1],
                              phase='final', kickoff=utc(FINAL_DATE))
        self.stdout.write(f"  Final: {winners[0]} vs {winners[1]}")

    # ── Standings printer ──────────────────────────────────────────────────

    def _print_standings(self):
        groups = sorted(set(
            NationalTeam.objects.filter(group__isnull=False)
            .values_list('group', flat=True).distinct()
        ))
        self.stdout.write(f"\n{'─'*60}\n  GROUP STANDINGS\n{'─'*60}")
        for g in groups:
            self.stdout.write(f"\n  Group {g}:")
            for i, row in enumerate(get_group_standings(g)):
                q = " ✓" if i < 2 else ""
                self.stdout.write(
                    f"    {i+1}. {row.team.flag} {row.team.name:<22} "
                    f"P{row.played} W{row.won} D{row.drawn} L{row.lost} "
                    f"GD{row.gd:+d} {row.points}pts{q}"
                )
