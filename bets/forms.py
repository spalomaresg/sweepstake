from django import forms
from .models import Bet

FIELD_CLASS = 'w-full px-4 py-2 rounded-lg bg-gray-800 border border-white/20 text-white placeholder-white/40 focus:outline-none focus:border-emerald-400'
SELECT_CLASS = FIELD_CLASS + ' [&>option]:bg-gray-800 [&>option]:text-white'


class BetForm(forms.ModelForm):
    class Meta:
        model = Bet
        fields = ['predicted_winner', 'predicted_home_goals', 'predicted_away_goals']

    def __init__(self, *args, match=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.match = match

        if match:
            home = str(match.home_team)
            away = str(match.away_team)
            choices = [
                ('',     '— Select winner —'),
                ('home', home),
                ('away', away),
                ('draw', 'Draw'),
            ]
        else:
            choices = [
                ('',     '— Select winner —'),
                ('home', 'Home'),
                ('away', 'Away'),
                ('draw', 'Draw'),
            ]

        self.fields['predicted_winner'].widget = forms.Select(
            choices=choices,
            attrs={'class': SELECT_CLASS}
        )
        self.fields['predicted_winner'].label = "Winner"

        if match and not match.allows_score_prediction:
            del self.fields['predicted_home_goals']
            del self.fields['predicted_away_goals']
        else:
            home_name = match.home_team.name if match else 'Home'
            away_name = match.away_team.name if match else 'Away'
            self.fields['predicted_home_goals'].widget.attrs.update(
                {'class': FIELD_CLASS, 'min': 0, 'placeholder': '0'})
            self.fields['predicted_home_goals'].label = f"Goals — {home_name}"
            self.fields['predicted_away_goals'].widget.attrs.update(
                {'class': FIELD_CLASS, 'min': 0, 'placeholder': '0'})
            self.fields['predicted_away_goals'].label = f"Goals — {away_name}"

    def clean(self):
        cleaned = super().clean()
        if self.match and self.match.allows_score_prediction:
            hg = cleaned.get('predicted_home_goals')
            ag = cleaned.get('predicted_away_goals')
            winner = cleaned.get('predicted_winner')
            if hg is None or ag is None:
                raise forms.ValidationError("You must enter an exact score for knockout matches.")
            if hg > ag and winner != 'home':
                raise forms.ValidationError("Winner does not match the exact score.")
            if ag > hg and winner != 'away':
                raise forms.ValidationError("Winner does not match the exact score.")
            if hg == ag and winner != 'draw':
                raise forms.ValidationError("If scores are level, select 'Draw' as the winner.")
        return cleaned
