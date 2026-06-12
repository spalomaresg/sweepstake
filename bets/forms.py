import csv
import os
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.conf import settings
from .models import Bet, SweepstakeTeam

FIELD_CLASS = 'w-full px-4 py-2 rounded-lg bg-gray-800 border border-white/20 text-white placeholder-white/40 focus:outline-none focus:border-emerald-400'
SELECT_CLASS = FIELD_CLASS + ' [&>option]:bg-gray-800 [&>option]:text-white'

VALID_EMAILS_PATH = os.path.join(settings.BASE_DIR, 'valid_emails.csv')


def load_valid_emails():
    """Return a dict of {email_lower: invite_code_lower} from valid_emails.csv."""
    result = {}
    try:
        with open(VALID_EMAILS_PATH, newline='', encoding='utf-8') as f:
            # Leemos una pequeña muestra del archivo para analizarla
            sample = f.read(2048)
            f.seek(0) # Volvemos a poner el puntero al principio del archivo
            
            # Intentamos detectar el delimitador automáticamente
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=[',', ';'])
                delimiter_found = dialect.delimiter
            except csv.Error:
                # Si el archivo tiene solo una línea o el "olfateador" duda,
                # usamos la coma como valor por defecto seguro
                delimiter_found = ','

            # Pasamos el delimitador dinámico al DictReader
            reader = csv.DictReader(f, delimiter=delimiter_found)
            for row in reader:
                email = row.get('email', '').strip().lower()
                code = row.get('invite_code', '').strip()
                if email:
                    result[email] = code
                    
    except FileNotFoundError:
        pass  # If file missing, no one can register (fail safe)
    return result


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="Email",
        help_text="Must match your invite email exactly."
    )
    invite_code = forms.CharField(
        required=True,
        label="Invite Code",
        help_text="The invite code provided alongside your email."
    )
    team = forms.ModelChoiceField(
        queryset=SweepstakeTeam.objects.all().order_by('name'),
        required=True,
        label="Your Team",
        empty_label="— Select your team —",
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'team':
                field.widget.attrs['class'] = SELECT_CLASS
            else:
                field.widget.attrs['class'] = FIELD_CLASS

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get('email', '').lower()
        invite_code = cleaned.get('invite_code', '').strip()

        valid_emails = load_valid_emails()

        if email not in valid_emails:
            self.add_error('email', "This email is not on the invite list.")
            return cleaned

        expected_code = valid_emails[email]
        if invite_code.lower() != expected_code.lower():
            self.add_error('invite_code', "Invalid invite code for this email.")
            return cleaned

        # Check uniqueness (belt-and-suspenders on top of DB constraint)
        if User.objects.filter(email__iexact=email).exists():
            self.add_error('email', "An account with this email already exists.")

        return cleaned

    def clean_email(self):
        return self.cleaned_data.get('email', '').lower()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'].lower()
        if commit:
            user.save()
        return user

    @property
    def selected_team(self):
        return self.cleaned_data.get('team')


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
