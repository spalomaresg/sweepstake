from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
import json

from .models import (Match, Bet, SweepstakeTeam, Profile, NationalTeam,
                     PHASE_CHOICES, PHASE_ORDER, POINTS_BY_PHASE,
                     get_bettable_phases, get_group_standings)
from .forms import BetForm, RegistrationForm


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


def home(request):
    if request.user.is_authenticated:
        return redirect('leaderboard')
    return render(request, 'bets/home.html')


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.team = form.selected_team
            profile.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}!')
            return redirect('leaderboard')
    else:
        form = RegistrationForm()
    from .models import SweepstakeTeam as BT
    return render(request, 'bets/register.html', {
        'form': form,
        'sweepstake_teams': BT.objects.all().order_by('name'),
    })


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            from .forms import load_valid_emails
            if not user.is_staff and user.email.lower() not in load_valid_emails():
                messages.error(request, 'Your email is not on the invite list.')
            else:
                login(request, user)
                return redirect('leaderboard')
        else:
            messages.error(request, 'Incorrect username or password.')
    else:
        form = AuthenticationForm()
    for field in form.fields.values():
        field.widget.attrs['class'] = (
            'w-full px-4 py-2 rounded-lg bg-gray-800 border border-white/20 '
            'text-white placeholder-white/40 focus:outline-none focus:border-emerald-400'
        )
    return render(request, 'bets/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


def _points_by_phase_for_user(user):
    return {
        phase_key: user.bets.filter(match__phase=phase_key).aggregate(
            t=Sum('points_earned'))['t'] or 0
        for phase_key, _ in PHASE_CHOICES
    }


def _points_by_phase_for_team(sweepstake_team):
    member_count = sweepstake_team.members.count()
    if not member_count:
        return {phase_key: 0 for phase_key, _ in PHASE_CHOICES}
    result = {}
    for phase_key, _ in PHASE_CHOICES:
        total = sum(
            m.user.bets.filter(match__phase=phase_key).aggregate(t=Sum('points_earned'))['t'] or 0
            for m in sweepstake_team.members.all()
        )
        result[phase_key] = round(total / member_count, 2)
    return result


@login_required
def leaderboard(request):
    active_phases = list(
        Match.objects.filter(finished=True)
        .values_list('phase', flat=True).distinct()
    )
    ordered_phases = [(k, label) for k, label in PHASE_CHOICES if k in active_phases]

    profiles = Profile.objects.select_related('user', 'team').filter(user__is_staff=False)
    individual_ranking = []
    for profile in profiles:
        phase_pts = _points_by_phase_for_user(profile.user)
        total = sum(phase_pts.values())
        correct = profile.user.bets.filter(points_earned__gt=0).count()
        placed = profile.user.bets.count()
        individual_ranking.append({
            'profile': profile, 'total': total,
            'correct': correct, 'placed': placed, 'phase_points': phase_pts,
        })
    individual_ranking.sort(key=lambda x: x['total'], reverse=True)

    teams = SweepstakeTeam.objects.all()
    team_ranking = []
    for t in teams:
        # Use model method which respects excluded_from_team_stats
        phase_pts = t.points_by_phase()
        avg_total = t.average_points
        team_ranking.append({
            'team': t,
            'average': avg_total,
            'total': t.total_points,
            'members': t._active_members().count(),
            'phase_points': phase_pts,
        })
    team_ranking.sort(key=lambda x: x['average'], reverse=True)

    return render(request, 'bets/leaderboard.html', {
        'individual_ranking': individual_ranking,
        'team_ranking': team_ranking,
        'active_phases': ordered_phases,
    })


@login_required
def my_predictions(request):
    now = timezone.now()
    bettable = get_bettable_phases()

    # Determine which phases to show:
    # - All phases that have matches, PLUS
    # - The next bettable phase even if it has no matches yet (shows "coming soon")
    phases_data = []
    shown_phases = set()

    for phase_key, phase_label in PHASE_CHOICES:
        all_matches = Match.objects.filter(phase=phase_key).select_related(
            'home_team', 'away_team').order_by('kickoff')
        has_matches = all_matches.exists()
        is_bettable = phase_key in bettable

        # Skip phases that have no matches AND are not bettable yet
        if not has_matches and not is_bettable:
            continue

        user_bets_qs = request.user.bets.filter(
            match__phase=phase_key
        ).select_related('match__home_team', 'match__away_team')
        bet_map = {b.match_id: b for b in user_bets_qs}

        pts = POINTS_BY_PHASE[phase_key]
        rows = []
        for match in all_matches:
            bet = bet_map.get(match.id)
            rows.append({
                'match': match,
                'bet': bet,
                'locked': now >= match.kickoff,
            })

        all_finished = has_matches and not Match.objects.filter(
            phase=phase_key, finished=False).exists()

        phases_data.append({
            'key': phase_key,
            'label': phase_label,
            'rows': rows,
            'has_matches': has_matches,
            'points_winner': pts[0],
            'points_exact': pts[1],
            'allows_score': phase_key != 'group_stage',
            'is_bettable': is_bettable,
            'is_complete': all_finished,
        })
        shown_phases.add(phase_key)

    total_points = request.user.bets.aggregate(t=Sum('points_earned'))['t'] or 0

    # Default to the last visible phase (most recent/active round)
    active_phase_key = phases_data[-1]['key'] if phases_data else None

    return render(request, 'bets/my_predictions.html', {
        'phases_data': phases_data,
        'total_points': total_points,
        'now': now,
        'active_phase_key': active_phase_key,
    })


@login_required
@require_POST
def save_prediction_ajax(request, match_id):
    """AJAX endpoint: save/update a bet inline from My Predictions page."""
    match = get_object_or_404(Match, id=match_id)
    now = timezone.now()

    if now >= match.kickoff:
        return JsonResponse({'ok': False, 'error': 'Match has already started.'}, status=400)

    bettable = get_bettable_phases()
    if match.phase not in bettable:
        return JsonResponse({'ok': False, 'error': 'Betting not open for this phase yet.'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid data.'}, status=400)

    predicted_winner = data.get('predicted_winner')
    predicted_home_goals = data.get('predicted_home_goals')
    predicted_away_goals = data.get('predicted_away_goals')

    valid_winners = {'home', 'away', 'draw'}
    if predicted_winner not in valid_winners:
        return JsonResponse({'ok': False, 'error': 'Invalid winner selection.'}, status=400)

    if match.allows_score_prediction:
        try:
            predicted_home_goals = int(predicted_home_goals)
            predicted_away_goals = int(predicted_away_goals)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Goals must be numbers.'}, status=400)
        # Knockout phases: no draws allowed — winner must be home or away
        # (equal score means it goes to penalties; winner reflects who advances)
        if predicted_home_goals > predicted_away_goals and predicted_winner != 'home':
            return JsonResponse({'ok': False, 'error': 'Winner does not match score.'}, status=400)
        if predicted_away_goals > predicted_home_goals and predicted_winner != 'away':
            return JsonResponse({'ok': False, 'error': 'Winner does not match score.'}, status=400)
        if predicted_home_goals == predicted_away_goals and predicted_winner not in ('home', 'away'):
            return JsonResponse({'ok': False, 'error': 'Please select who wins on penalties.'}, status=400)
    else:
        predicted_home_goals = None
        predicted_away_goals = None

    bet, _ = Bet.objects.update_or_create(
        user=request.user,
        match=match,
        defaults={
            'predicted_winner': predicted_winner,
            'predicted_home_goals': predicted_home_goals,
            'predicted_away_goals': predicted_away_goals,
        }
    )
    return JsonResponse({'ok': True, 'bet_id': bet.id})


@login_required
def group_standings(request):
    """Show live group standings for all groups."""
    groups = sorted(set(
        NationalTeam.objects.filter(group__isnull=False)
        .values_list('group', flat=True).distinct()
    ))
    standings = {g: get_group_standings(g) for g in groups}
    return render(request, 'bets/group_standings.html', {'standings': standings})
