from django.db import models, transaction
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class Sweepstake(models.Model):
    name = models.CharField(max_length=100)
    invite_code = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Sweepstake"
        verbose_name_plural = "Sweepstakes"
        ordering = ['name']


class SweepstakeTeam(models.Model):
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#3B82F6')
    sweepstake = models.ForeignKey(
        Sweepstake, on_delete=models.CASCADE, related_name='teams',
        null=True, blank=True,
    )

    def __str__(self):
        return self.name

    def _active_members(self):
        """SweepstakeMembership rows counted in team stats (not excluded)."""
        return self.members.filter(excluded_from_team_stats=False)

    @property
    def average_points(self):
        members = self._active_members()
        count = members.count()
        if not count:
            return 0
        total = sum(m.user.bets.aggregate(t=models.Sum('points_earned'))['t'] or 0 for m in members)
        return round(total / count, 2)

    @property
    def total_points(self):
        return sum(
            m.user.bets.aggregate(t=models.Sum('points_earned'))['t'] or 0
            for m in self._active_members()
        )

    def points_by_phase(self):
        members = self._active_members()
        count = members.count()
        result = {}
        for phase_key, _ in PHASE_CHOICES:
            total = sum(
                m.user.bets.filter(match__phase=phase_key).aggregate(t=models.Sum('points_earned'))['t'] or 0
                for m in members
            )
            result[phase_key] = round(total / count, 2) if count else 0
        return result

    class Meta:
        verbose_name = "Sweepstake Team"
        verbose_name_plural = "Sweepstake Teams"
        ordering = ['name']


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    # Legacy fields — team assignment now lives in SweepstakeMembership
    team = models.ForeignKey(
        SweepstakeTeam, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='legacy_members',
    )
    excluded_from_team_stats = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile of {self.user.username}"

    @property
    def total_points(self):
        return self.user.bets.aggregate(t=models.Sum('points_earned'))['t'] or 0

    def points_by_phase(self):
        return {
            phase_key: self.user.bets.filter(match__phase=phase_key).aggregate(
                t=models.Sum('points_earned')
            )['t'] or 0
            for phase_key, _ in PHASE_CHOICES
        }

    class Meta:
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"


class SweepstakeMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    sweepstake = models.ForeignKey(Sweepstake, on_delete=models.CASCADE, related_name='memberships')
    team = models.ForeignKey(
        SweepstakeTeam, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='members',
    )
    excluded_from_team_stats = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} — {self.sweepstake.name}"

    class Meta:
        unique_together = ('user', 'sweepstake')
        verbose_name = "Sweepstake Membership"
        verbose_name_plural = "Sweepstake Memberships"
        ordering = ['sweepstake__name', 'user__username']


class NationalTeam(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3)
    group = models.CharField(max_length=1, blank=True, null=True)
    flag = models.CharField(max_length=10, blank=True, default='')

    def __str__(self):
        if self.flag:
            return f"{self.flag} {self.name}"
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "National Team"
        verbose_name_plural = "National Teams"


PHASE_CHOICES = [
    ('group_stage',   _('Group Stage')),
    ('round_of_32',   _('Round of 32')),
    ('round_of_16',   _('Round of 16')),
    ('quarterfinals', _('Quarter-finals')),
    ('semifinals',    _('Semi-finals')),
    ('third_place',   _('Third Place')),
    ('final',         _('Final')),
]

PHASE_ORDER = [p[0] for p in PHASE_CHOICES]

# Phases that can be bet on simultaneously (once semis are done)
CONCURRENT_PHASES = {'third_place', 'final'}

# (points_winner, points_exact)
POINTS_BY_PHASE = {
    'group_stage':   (1, None),
    'round_of_32':   (1, 2),
    'round_of_16':   (1, 2),
    'quarterfinals': (1, 2),
    'semifinals':    (2, 4),
    'third_place':   (2, 4),
    'final':         (5, 10),
}




def auto_create_next_phase_matches():
    """
    Called after any match is marked finished.
    If a phase just completed, create the bracket matches for the next phase
    so users can immediately place bets.
    """
    from bets.management.commands.simulate_phase import Command as SimCmd
    import io
    cmd = SimCmd()
    cmd.stdout = io.StringIO()

    for i, phase_key in enumerate(PHASE_ORDER[:-1]):
        phase_matches = Match.objects.filter(phase=phase_key)
        if not phase_matches.exists():
            continue
        all_done = not phase_matches.filter(finished=False).exists()
        if not all_done:
            break
        next_phase = PHASE_ORDER[i + 1]
        if phase_key == 'semifinals':
            if not Match.objects.filter(phase='third_place').exists():
                cmd._create_third_place()
            if not Match.objects.filter(phase='final').exists():
                cmd._create_final()
            break
        else:
            if not Match.objects.filter(phase=next_phase).exists():
                cmd._create_matches_only(next_phase)
            break


class GroupStanding:
    """In-memory group standings calculated from finished matches."""
    def __init__(self, team):
        self.team = team
        self.played = 0
        self.won = 0
        self.drawn = 0
        self.lost = 0
        self.gf = 0
        self.ga = 0

    @property
    def gd(self):
        return self.gf - self.ga

    @property
    def points(self):
        return self.won * 3 + self.drawn


def get_group_standings(group_letter):
    """Calculate current standings for a group from finished match results."""
    teams = NationalTeam.objects.filter(group=group_letter)
    stats = {t.id: GroupStanding(t) for t in teams}

    matches = Match.objects.filter(
        phase='group_stage',
        home_team__group=group_letter,
        finished=True,
        home_goals__isnull=False,
    ).select_related('home_team', 'away_team')

    for m in matches:
        h = stats.get(m.home_team_id)
        a = stats.get(m.away_team_id)
        if not h or not a:
            continue
        h.played += 1
        a.played += 1
        h.gf += m.home_goals
        h.ga += m.away_goals
        a.gf += m.away_goals
        a.ga += m.home_goals
        if m.home_goals > m.away_goals:
            h.won += 1; a.lost += 1
        elif m.away_goals > m.home_goals:
            a.won += 1; h.lost += 1
        else:
            h.drawn += 1; a.drawn += 1

    standings = sorted(
        stats.values(),
        key=lambda s: (s.points, s.gd, s.gf),
        reverse=True
    )
    return standings


class Match(models.Model):
    home_team = models.ForeignKey(NationalTeam, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(NationalTeam, on_delete=models.CASCADE, related_name='away_matches')
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES)
    kickoff = models.DateTimeField()
    home_goals = models.IntegerField(null=True, blank=True)
    away_goals = models.IntegerField(null=True, blank=True)
    penalty_home_goals = models.IntegerField(null=True, blank=True)
    penalty_away_goals = models.IntegerField(null=True, blank=True)
    knockout_winner = models.CharField(max_length=4, null=True, blank=True,
        help_text="Knockout only: who advanced (home/away) after extra time/pens")
    finished = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} ({self.get_phase_display()})"

    @property
    def is_knockout(self):
        return self.phase != 'group_stage'

    @property
    def allows_score_prediction(self):
        return self.phase != 'group_stage'

    @property
    def winner(self):
        """For group stage: based on goals. For knockout: uses knockout_winner if set, else goals."""
        if not self.finished:
            return None
        if self.is_knockout and self.knockout_winner:
            return self.knockout_winner
        if self.home_goals is None or self.away_goals is None:
            return None
        if self.home_goals > self.away_goals:
            return 'home'
        elif self.away_goals > self.home_goals:
            return 'away'
        return 'draw'

    @property
    def points_for_winner(self):
        return POINTS_BY_PHASE[self.phase][0]

    @property
    def points_for_exact(self):
        return POINTS_BY_PHASE[self.phase][1]

    def calculate_bet_points(self, bet):
        if not self.finished:
            return 0
        pts_winner, pts_exact = POINTS_BY_PHASE[self.phase]
        points = 0
        if bet.predicted_winner == self.winner:
            points += pts_winner
        if pts_exact and self.home_goals is not None and (
                bet.predicted_home_goals == self.home_goals and
                bet.predicted_away_goals == self.away_goals):
            points += pts_exact
        return points

    class Meta:
        ordering = ['kickoff']
        verbose_name = "Match"
        verbose_name_plural = "Matches"


class Bet(models.Model):
    WINNER_CHOICES = [
        ('home', 'Home Win'),
        ('away', 'Away Win'),
        ('draw', 'Draw'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bets')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='bets')
    predicted_winner = models.CharField(max_length=10, choices=WINNER_CHOICES)
    predicted_home_goals = models.IntegerField(null=True, blank=True)
    predicted_away_goals = models.IntegerField(null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    points_earned = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} — {self.match}"

    class Meta:
        unique_together = ('user', 'match')
        verbose_name = "Bet"
        verbose_name_plural = "Bets"


@receiver(post_save, sender=Match)
def update_bet_points_on_finish(sender, instance, **kwargs):
    if not instance.finished:
        return
    bets = list(instance.bets.all())
    if not bets:
        return
    for bet in bets:
        bet.points_earned = instance.calculate_bet_points(bet)
    with transaction.atomic():
        for bet in bets:
            bet.save(update_fields=['points_earned'])
