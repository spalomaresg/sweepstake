from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import SweepstakeTeam, Profile, NationalTeam, Match, Bet


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('team', 'excluded_from_team_stats')


class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(SweepstakeTeam)
class SweepstakeTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'color_preview', 'num_members', 'average_points']

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


@admin.register(NationalTeam)
class NationalTeamAdmin(admin.ModelAdmin):
    list_display = ['flag', 'name', 'code', 'group']
    list_filter = ['group']
    search_fields = ['name', 'code']


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'phase', 'kickoff', 'score', 'home_goals',
                    'away_goals', 'knockout_winner', 'finished']
    list_filter = ['phase', 'finished']
    list_editable = ['home_goals', 'away_goals', 'knockout_winner', 'finished']
    ordering = ['kickoff']
    help_text = (
        "For knockout matches that go to extra time/penalties: set home_goals and away_goals "
        "to the 90-min score, then set knockout_winner to who actually advanced."
    )

    def score(self, obj):
        if obj.home_goals is not None and obj.away_goals is not None:
            suffix = f" ({obj.knockout_winner} adv.)" if obj.knockout_winner and obj.home_goals == obj.away_goals else ""
            return format_html('<strong>{} – {}</strong>{}', obj.home_goals, obj.away_goals, suffix)
        return '—'
    score.short_description = 'Score'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.finished:
            for bet in obj.bets.all():
                bet.points_earned = obj.calculate_bet_points(bet)
                bet.save()



@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ['user', 'match', 'predicted_winner',
                    'predicted_home_goals', 'predicted_away_goals', 'points_earned']
    list_filter = ['match__phase']
    readonly_fields = ['points_earned', 'placed_at']
