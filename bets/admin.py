from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import Sweepstake, SweepstakeMembership, SweepstakeTeam, Profile, NationalTeam, Match, Bet


# ── Sweepstake ────────────────────────────────────────────────────────────────

class SweepstakeMembershipInline(admin.TabularInline):
    model = SweepstakeMembership
    extra = 0
    fields = ('user', 'team', 'excluded_from_team_stats', 'joined_at')
    readonly_fields = ('joined_at',)
    autocomplete_fields = ('user',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'team':
            sweepstake_id = request.resolver_match.kwargs.get('object_id')
            if sweepstake_id:
                kwargs['queryset'] = SweepstakeTeam.objects.filter(sweepstake_id=sweepstake_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Sweepstake)
class SweepstakeAdmin(admin.ModelAdmin):
    list_display = ['name', 'invite_code', 'member_count', 'created_at']
    readonly_fields = ['created_at']
    inlines = [SweepstakeMembershipInline]

    def member_count(self, obj):
        return obj.memberships.count()
    member_count.short_description = 'Members'


# ── Users + memberships ───────────────────────────────────────────────────────

class UserMembershipInline(admin.TabularInline):
    model = SweepstakeMembership
    extra = 0
    fields = ('sweepstake', 'team', 'excluded_from_team_stats', 'joined_at')
    readonly_fields = ('joined_at',)
    verbose_name = "Sweepstake membership"
    verbose_name_plural = "Sweepstake memberships"


class UserAdmin(BaseUserAdmin):
    inlines = (UserMembershipInline,)
    search_fields = ('username', 'first_name', 'last_name', 'email')


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ── Sweepstake Teams ──────────────────────────────────────────────────────────

@admin.register(SweepstakeTeam)
class SweepstakeTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'sweepstake', 'color_preview', 'num_members', 'average_points']
    list_filter = ['sweepstake']

    def color_preview(self, obj):
        return format_html(
            '<span style="display:inline-block;width:18px;height:18px;background:{};'
            'border-radius:3px;vertical-align:middle;"></span> {}', obj.color, obj.color)
    color_preview.short_description = 'Color'

    def num_members(self, obj):
        return obj.members.count()
    num_members.short_description = 'Members'

    def average_points(self, obj):
        return obj.average_points
    average_points.short_description = 'Avg Points'


# ── National Teams + Matches + Bets ──────────────────────────────────────────

@admin.register(NationalTeam)
class NationalTeamAdmin(admin.ModelAdmin):
    list_display = ['flag', 'name', 'code', 'group']
    list_filter = ['group']
    search_fields = ['name', 'code']


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'phase', 'kickoff', 'score', 'home_goals',
                    'away_goals', 'penalty_home_goals', 'penalty_away_goals',
                    'knockout_winner', 'finished']
    list_filter = ['phase', 'finished']
    list_editable = ['home_goals', 'away_goals', 'penalty_home_goals', 'penalty_away_goals',
                     'knockout_winner', 'finished']
    ordering = ['kickoff']

    def score(self, obj):
        if obj.home_goals is not None and obj.away_goals is not None:
            if obj.knockout_winner and obj.home_goals == obj.away_goals and obj.penalty_home_goals is not None:
                return format_html('<strong>{} ({}) – {} ({})</strong>',
                                   obj.home_goals, obj.penalty_home_goals,
                                   obj.away_goals, obj.penalty_away_goals)
            suffix = f" ({obj.knockout_winner} adv.)" if obj.knockout_winner and obj.home_goals == obj.away_goals else ""
            return format_html('<strong>{} – {}</strong>{}', obj.home_goals, obj.away_goals, suffix)
        return '—'
    score.short_description = 'Score'


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ['user', 'match', 'predicted_winner',
                    'predicted_home_goals', 'predicted_away_goals', 'points_earned']
    list_filter = ['match__phase']
    readonly_fields = ['points_earned', 'placed_at']
