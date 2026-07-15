from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
import json

from .models import (Match, Bet, SweepstakeTeam, Profile, NationalTeam,
                     Sweepstake, SweepstakeMembership,
                     PHASE_CHOICES, PHASE_ORDER, POINTS_BY_PHASE,
                     get_group_standings)
from .forms import BetForm


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


def home(request):
    if request.user.is_authenticated:
        return redirect('leaderboard')
    return render(request, 'bets/home.html')


def _clear_reg_session(request):
    for key in ['reg_username', 'reg_sweepstake_id']:
        request.session.pop(key, None)


def register(request):
    invite_param = request.GET.get('invite', '').strip()

    if request.method == 'GET':
        _clear_reg_session(request)
        return render(request, 'bets/register.html', {
            'stage': 'initial',
            'invite_param': invite_param,
        })

    stage = request.POST.get('stage', 'initial')

    # ── Stage 1: validate username + invite code ──────────────────────────────
    if stage == 'initial':
        username = request.POST.get('username', '').strip()
        invite_code = request.POST.get('invite_code', '').strip()
        errors = {}

        if not username:
            errors['username'] = _('Username is required.')

        sweepstake = None
        if not invite_code:
            errors['invite_code'] = _('Invite code is required.')
        else:
            try:
                sweepstake = Sweepstake.objects.get(invite_code__iexact=invite_code)
            except Sweepstake.DoesNotExist:
                errors['invite_code'] = _('Invalid invite code.')

        if errors:
            return render(request, 'bets/register.html', {
                'stage': 'initial',
                'invite_param': invite_code,
                'errors': errors,
                'username_value': username,
            })

        user_exists = User.objects.filter(username__iexact=username).exists()

        if user_exists:
            existing_user = User.objects.get(username__iexact=username)
            if SweepstakeMembership.objects.filter(user=existing_user, sweepstake=sweepstake).exists():
                errors['invite_code'] = _('You are already a member of this sweepstake.')
                return render(request, 'bets/register.html', {
                    'stage': 'initial',
                    'invite_param': invite_code,
                    'errors': errors,
                    'username_value': username,
                })

        request.session['reg_username'] = username
        request.session['reg_sweepstake_id'] = sweepstake.id

        if user_exists:
            return render(request, 'bets/register.html', {
                'stage': 'login',
                'username': username,
                'sweepstake': sweepstake,
            })
        else:
            teams = SweepstakeTeam.objects.filter(sweepstake=sweepstake).order_by('name')
            return render(request, 'bets/register.html', {
                'stage': 'new',
                'username': username,
                'sweepstake': sweepstake,
                'sweepstake_teams': teams,
            })

    # ── Stage 2a: existing user — password check ──────────────────────────────
    elif stage == 'login':
        username = request.session.get('reg_username')
        sweepstake_id = request.session.get('reg_sweepstake_id')
        if not username or not sweepstake_id:
            return redirect('register')

        sweepstake = get_object_or_404(Sweepstake, id=sweepstake_id)
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if not user:
            return render(request, 'bets/register.html', {
                'stage': 'login',
                'username': username,
                'sweepstake': sweepstake,
                'errors': {'password': _('Incorrect password.')},
            })

        SweepstakeMembership.objects.get_or_create(user=user, sweepstake=sweepstake)
        login(request, user)
        _clear_reg_session(request)
        messages.success(
            request,
            _('Welcome back! You have joined %(sweepstake)s.') % {'sweepstake': sweepstake.name}
        )
        return redirect('leaderboard')

    # ── Stage 2b: new user — full registration ────────────────────────────────
    elif stage == 'new':
        username = request.session.get('reg_username')
        sweepstake_id = request.session.get('reg_sweepstake_id')
        if not username or not sweepstake_id:
            return redirect('register')

        sweepstake = get_object_or_404(Sweepstake, id=sweepstake_id)
        teams = SweepstakeTeam.objects.filter(sweepstake=sweepstake).order_by('name')

        name = request.POST.get('name', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        team_id = request.POST.get('team', '').strip()
        errors = {}

        if not name:
            errors['name'] = _('Name is required.')

        if not password1:
            errors['password1'] = _('Password is required.')
        elif len(password1) < 8:
            errors['password1'] = _('Password must be at least 8 characters.')
        elif password1 != password2:
            errors['password2'] = _('Passwords do not match.')

        if User.objects.filter(username__iexact=username).exists():
            errors['non_field'] = _('This username was just taken. Please start over.')

        team = None
        if team_id:
            try:
                team = SweepstakeTeam.objects.get(id=team_id, sweepstake=sweepstake)
            except SweepstakeTeam.DoesNotExist:
                errors['team'] = _('Invalid team selection.')

        if errors:
            return render(request, 'bets/register.html', {
                'stage': 'new',
                'username': username,
                'sweepstake': sweepstake,
                'sweepstake_teams': teams,
                'errors': errors,
                'name_value': name,
            })

        user = User.objects.create_user(username=username, password=password1)
        if name:
            parts = name.split(' ', 1)
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = parts[1]
            user.save()

        Profile.objects.get_or_create(user=user)
        SweepstakeMembership.objects.create(user=user, sweepstake=sweepstake, team=team)
        login(request, user)
        _clear_reg_session(request)
        messages.success(request, _('Welcome, %(username)s!') % {'username': user.username})
        return redirect('leaderboard')

    return redirect('register')


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('leaderboard')
        else:
            messages.error(request, _('Incorrect username or password.'))
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


@login_required
def leaderboard(request):
    active_phases = list(
        Match.objects.filter(finished=True)
        .values_list('phase', flat=True).distinct()
    )
    ordered_phases = [(k, label) for k, label in PHASE_CHOICES if k in active_phases]

    user_sweepstake_ids = SweepstakeMembership.objects.filter(
        user=request.user
    ).values_list('sweepstake_id', flat=True)
    user_sweepstakes = list(Sweepstake.objects.filter(id__in=user_sweepstake_ids).order_by('name'))

    sweepstake_data = []
    for sweepstake in user_sweepstakes:
        memberships = (
            SweepstakeMembership.objects
            .filter(sweepstake=sweepstake)
            .select_related('user', 'team')
        )

        individual_ranking = []
        for membership in memberships:
            phase_pts = _points_by_phase_for_user(membership.user)
            total = sum(phase_pts.values())
            individual_ranking.append({
                'membership': membership,
                'total': total,
                'phase_points': phase_pts,
            })
        individual_ranking.sort(key=lambda x: x['total'], reverse=True)

        teams = SweepstakeTeam.objects.filter(sweepstake=sweepstake)
        team_ranking = []
        for t in teams:
            phase_pts = t.points_by_phase()
            average = round(sum(phase_pts.get(k, 0) for k, _ in ordered_phases), 2)
            team_ranking.append({
                'team': t,
                'average': average,
                'members': t._active_members().count(),
                'phase_points': phase_pts,
            })
        team_ranking.sort(key=lambda x: x['average'], reverse=True)

        has_sweepstake_teams = teams.exists()
        show_teams_tab = has_sweepstake_teams and memberships.filter(team__isnull=False).exists()

        sweepstake_data.append({
            'sweepstake': sweepstake,
            'individual_ranking': individual_ranking,
            'team_ranking': team_ranking,
            'has_sweepstake_teams': has_sweepstake_teams,
            'show_teams_tab': show_teams_tab,
        })

    return render(request, 'bets/leaderboard.html', {
        'sweepstake_data': sweepstake_data,
        'active_phases': ordered_phases,
        'show_sweepstake_tabs': len(user_sweepstakes) > 1,
    })


@login_required
def my_predictions(request):
    now = timezone.now()

    phases_data = []
    phase_label_map = dict(PHASE_CHOICES)
    combined_keys = {'third_place', 'final'}

    for phase_key, phase_label in PHASE_CHOICES:
        if phase_key in combined_keys:
            continue

        all_matches = Match.objects.filter(phase=phase_key).select_related(
            'home_team', 'away_team').order_by('kickoff')
        has_matches = all_matches.exists()
        is_bettable = all_matches.filter(kickoff__gt=now).exists()

        if not has_matches:
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
            'points_winner': pts[0],
            'points_exact': pts[1],
            'allows_score': phase_key != 'group_stage',
            'is_bettable': is_bettable,
            'is_complete': all_finished,
            'is_combined': False,
        })

    # Combined Final & Third Place tab
    combined_matches = Match.objects.filter(
        phase__in=list(combined_keys)
    ).select_related('home_team', 'away_team').order_by('kickoff')
    if combined_matches.exists():
        user_bets_combined = request.user.bets.filter(
            match__phase__in=list(combined_keys)
        ).select_related('match__home_team', 'match__away_team')
        bet_map_combined = {b.match_id: b for b in user_bets_combined}
        rows = []
        for match in combined_matches:
            bet = bet_map_combined.get(match.id)
            pts = POINTS_BY_PHASE[match.phase]
            rows.append({
                'match': match,
                'bet': bet,
                'locked': now >= match.kickoff,
                'phase_label': phase_label_map[match.phase],
                'points_winner': pts[0],
                'points_exact': pts[1],
            })
        is_bettable = combined_matches.filter(kickoff__gt=now).exists()
        all_finished = not combined_matches.filter(finished=False).exists()
        phases_data.append({
            'key': 'final_stages',
            'label': _('Final & Third Place'),
            'rows': rows,
            'points_winner': None,
            'points_exact': None,
            'allows_score': True,
            'is_bettable': is_bettable,
            'is_complete': all_finished,
            'is_combined': True,
            'third_place_pts': POINTS_BY_PHASE['third_place'],
            'final_pts': POINTS_BY_PHASE['final'],
        })

    total_points = request.user.bets.aggregate(t=Sum('points_earned'))['t'] or 0
    active_phase_key = next(
        (p['key'] for p in phases_data if not p['is_complete']),
        phases_data[-1]['key'] if phases_data else None,
    )

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
        return JsonResponse({'ok': False, 'error': _('Match has already started.')}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': _('Invalid data.')}, status=400)

    predicted_winner = data.get('predicted_winner')
    predicted_home_goals = data.get('predicted_home_goals')
    predicted_away_goals = data.get('predicted_away_goals')

    valid_winners = {'home', 'away', 'draw'}
    if predicted_winner not in valid_winners:
        return JsonResponse({'ok': False, 'error': _('Invalid winner selection.')}, status=400)

    if match.allows_score_prediction:
        try:
            predicted_home_goals = int(predicted_home_goals)
            predicted_away_goals = int(predicted_away_goals)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': _('Goals must be numbers.')}, status=400)
        if predicted_home_goals > predicted_away_goals and predicted_winner != 'home':
            return JsonResponse({'ok': False, 'error': _('Winner does not match score.')}, status=400)
        if predicted_away_goals > predicted_home_goals and predicted_winner != 'away':
            return JsonResponse({'ok': False, 'error': _('Winner does not match score.')}, status=400)
        if predicted_home_goals == predicted_away_goals and predicted_winner not in ('home', 'away'):
            return JsonResponse({'ok': False, 'error': _('Please select who wins on penalties.')}, status=400)
    else:
        predicted_home_goals = None
        predicted_away_goals = None

    bet, _created = Bet.objects.update_or_create(
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
