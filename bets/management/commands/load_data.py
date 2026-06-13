"""
Load all confirmed FIFA World Cup 2026 group stage teams and matches.
Run: python manage.py load_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from bets.models import NationalTeam, Match
import datetime

# (name, code, group, flag)
TEAMS = [
    ("Mexico",               "MEX", "A", "🇲🇽"),
    ("South Korea",          "KOR", "A", "🇰🇷"),
    ("Czechia",              "CZE", "A", "🇨🇿"),
    ("South Africa",         "RSA", "A", "🇿🇦"),

    ("Switzerland",          "SUI", "B", "🇨🇭"),
    ("Canada",               "CAN", "B", "🇨🇦"),
    ("Qatar",                "QAT", "B", "🇶🇦"),
    ("Bosnia & Herzegovina", "BIH", "B", "🇧🇦"),

    ("Brazil",               "BRA", "C", "🇧🇷"),
    ("Morocco",              "MAR", "C", "🇲🇦"),
    ("Haiti",                "HAI", "C", "🇭🇹"),
    ("Scotland",             "SCO", "C", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),

    ("USA",                  "USA", "D", "🇺🇸"),
    ("Turkey",               "TUR", "D", "🇹🇷"),
    ("Australia",            "AUS", "D", "🇦🇺"),
    ("Paraguay",             "PAR", "D", "🇵🇾"),

    ("Germany",              "GER", "E", "🇩🇪"),
    ("Ecuador",              "ECU", "E", "🇪🇨"),
    ("Ivory Coast",          "CIV", "E", "🇨🇮"),
    ("Curacao",              "CUW", "E", "🇨🇼"),

    ("Netherlands",          "NED", "F", "🇳🇱"),
    ("Japan",                "JPN", "F", "🇯🇵"),
    ("Sweden",               "SWE", "F", "🇸🇪"),
    ("Tunisia",              "TUN", "F", "🇹🇳"),

    ("Belgium",              "BEL", "G", "🇧🇪"),
    ("Egypt",                "EGY", "G", "🇪🇬"),
    ("Iran",                 "IRN", "G", "🇮🇷"),
    ("New Zealand",          "NZL", "G", "🇳🇿"),

    ("Spain",                "ESP", "H", "🇪🇸"),
    ("Cape Verde",           "CPV", "H", "🇨🇻"),
    ("Saudi Arabia",         "KSA", "H", "🇸🇦"),
    ("Uruguay",              "URU", "H", "🇺🇾"),

    ("France",               "FRA", "I", "🇫🇷"),
    ("Senegal",              "SEN", "I", "🇸🇳"),
    ("Iraq",                 "IRQ", "I", "🇮🇶"),
    ("Norway",               "NOR", "I", "🇳🇴"),

    ("Argentina",            "ARG", "J", "🇦🇷"),
    ("Algeria",              "ALG", "J", "🇩🇿"),
    ("Austria",              "AUT", "J", "🇦🇹"),
    ("Jordan",               "JOR", "J", "🇯🇴"),

    ("Portugal",             "POR", "K", "🇵🇹"),
    ("DR Congo",             "COD", "K", "🇨🇩"),
    ("Uzbekistan",           "UZB", "K", "🇺🇿"),
    ("Colombia",             "COL", "K", "🇨🇴"),

    ("England",              "ENG", "L", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    ("Croatia",              "CRO", "L", "🇭🇷"),
    ("Ghana",                "GHA", "L", "🇬🇭"),
    ("Panama",               "PAN", "L", "🇵🇦"),
]

# All 72 group stage matches — UTC times sourced from football-data.org API.
# (home, away, phase, "YYYY-MM-DD HH:MM" UTC)
MATCHES = [
    # GROUP A
    ("Mexico",                  "South Africa",         "group_stage", "2026-06-11 19:00"),
    ("South Korea",             "Czechia",              "group_stage", "2026-06-12 02:00"),
    ("Czechia",                 "South Africa",         "group_stage", "2026-06-18 16:00"),
    ("Mexico",                  "South Korea",          "group_stage", "2026-06-19 01:00"),
    ("Czechia",                 "Mexico",               "group_stage", "2026-06-25 01:00"),
    ("South Africa",            "South Korea",          "group_stage", "2026-06-25 01:00"),

    # GROUP B
    ("Canada",                  "Bosnia & Herzegovina", "group_stage", "2026-06-12 19:00"),
    ("Qatar",                   "Switzerland",          "group_stage", "2026-06-13 19:00"),
    ("Switzerland",             "Bosnia & Herzegovina", "group_stage", "2026-06-18 19:00"),
    ("Canada",                  "Qatar",                "group_stage", "2026-06-18 22:00"),
    ("Switzerland",             "Canada",               "group_stage", "2026-06-24 19:00"),
    ("Bosnia & Herzegovina",    "Qatar",                "group_stage", "2026-06-24 19:00"),

    # GROUP C
    ("Brazil",                  "Morocco",              "group_stage", "2026-06-13 22:00"),
    ("Haiti",                   "Scotland",             "group_stage", "2026-06-14 01:00"),
    ("Scotland",                "Morocco",              "group_stage", "2026-06-19 22:00"),
    ("Brazil",                  "Haiti",                "group_stage", "2026-06-20 00:30"),
    ("Morocco",                 "Haiti",                "group_stage", "2026-06-24 22:00"),
    ("Scotland",                "Brazil",               "group_stage", "2026-06-24 22:00"),

    # GROUP D
    ("USA",                     "Paraguay",             "group_stage", "2026-06-13 01:00"),
    ("Australia",               "Turkey",               "group_stage", "2026-06-14 04:00"),
    ("USA",                     "Australia",            "group_stage", "2026-06-19 19:00"),
    ("Turkey",                  "Paraguay",             "group_stage", "2026-06-20 03:00"),
    ("Turkey",                  "USA",                  "group_stage", "2026-06-26 02:00"),
    ("Paraguay",                "Australia",            "group_stage", "2026-06-26 02:00"),

    # GROUP E
    ("Germany",                 "Curacao",              "group_stage", "2026-06-14 17:00"),
    ("Ivory Coast",             "Ecuador",              "group_stage", "2026-06-14 23:00"),
    ("Germany",                 "Ivory Coast",          "group_stage", "2026-06-20 20:00"),
    ("Ecuador",                 "Curacao",              "group_stage", "2026-06-21 00:00"),
    ("Ecuador",                 "Germany",              "group_stage", "2026-06-25 20:00"),
    ("Curacao",                 "Ivory Coast",          "group_stage", "2026-06-25 20:00"),

    # GROUP F
    ("Netherlands",             "Japan",                "group_stage", "2026-06-14 20:00"),
    ("Sweden",                  "Tunisia",              "group_stage", "2026-06-15 02:00"),
    ("Netherlands",             "Sweden",               "group_stage", "2026-06-20 17:00"),
    ("Tunisia",                 "Japan",                "group_stage", "2026-06-21 04:00"),
    ("Tunisia",                 "Netherlands",          "group_stage", "2026-06-25 23:00"),
    ("Japan",                   "Sweden",               "group_stage", "2026-06-25 23:00"),

    # GROUP G
    ("Belgium",                 "Egypt",                "group_stage", "2026-06-15 19:00"),
    ("Iran",                    "New Zealand",          "group_stage", "2026-06-16 01:00"),
    ("Belgium",                 "Iran",                 "group_stage", "2026-06-21 19:00"),
    ("New Zealand",             "Egypt",                "group_stage", "2026-06-22 01:00"),
    ("New Zealand",             "Belgium",              "group_stage", "2026-06-27 03:00"),
    ("Egypt",                   "Iran",                 "group_stage", "2026-06-27 03:00"),

    # GROUP H
    ("Spain",                   "Cape Verde",           "group_stage", "2026-06-15 16:00"),
    ("Saudi Arabia",            "Uruguay",              "group_stage", "2026-06-15 22:00"),
    ("Spain",                   "Saudi Arabia",         "group_stage", "2026-06-21 16:00"),
    ("Uruguay",                 "Cape Verde",           "group_stage", "2026-06-21 22:00"),
    ("Uruguay",                 "Spain",                "group_stage", "2026-06-27 00:00"),
    ("Cape Verde",              "Saudi Arabia",         "group_stage", "2026-06-27 00:00"),

    # GROUP I
    ("France",                  "Senegal",              "group_stage", "2026-06-16 19:00"),
    ("Iraq",                    "Norway",               "group_stage", "2026-06-16 22:00"),
    ("France",                  "Iraq",                 "group_stage", "2026-06-22 21:00"),
    ("Norway",                  "Senegal",              "group_stage", "2026-06-23 00:00"),
    ("Norway",                  "France",               "group_stage", "2026-06-26 19:00"),
    ("Senegal",                 "Iraq",                 "group_stage", "2026-06-26 19:00"),

    # GROUP J
    ("Argentina",               "Algeria",              "group_stage", "2026-06-17 01:00"),
    ("Austria",                 "Jordan",               "group_stage", "2026-06-17 04:00"),
    ("Argentina",               "Austria",              "group_stage", "2026-06-22 17:00"),
    ("Jordan",                  "Algeria",              "group_stage", "2026-06-23 03:00"),
    ("Jordan",                  "Argentina",            "group_stage", "2026-06-28 02:00"),
    ("Algeria",                 "Austria",              "group_stage", "2026-06-28 02:00"),

    # GROUP K
    ("Portugal",                "DR Congo",             "group_stage", "2026-06-17 17:00"),
    ("Uzbekistan",              "Colombia",             "group_stage", "2026-06-18 02:00"),
    ("Portugal",                "Uzbekistan",           "group_stage", "2026-06-23 17:00"),
    ("Colombia",                "DR Congo",             "group_stage", "2026-06-24 02:00"),
    ("Colombia",                "Portugal",             "group_stage", "2026-06-27 23:30"),
    ("DR Congo",                "Uzbekistan",           "group_stage", "2026-06-27 23:30"),

    # GROUP L
    ("England",                 "Croatia",              "group_stage", "2026-06-17 20:00"),
    ("Ghana",                   "Panama",               "group_stage", "2026-06-17 23:00"),
    ("England",                 "Ghana",                "group_stage", "2026-06-23 20:00"),
    ("Panama",                  "Croatia",              "group_stage", "2026-06-23 23:00"),
    ("Panama",                  "England",              "group_stage", "2026-06-27 21:00"),
    ("Croatia",                 "Ghana",                "group_stage", "2026-06-27 21:00"),
]


class Command(BaseCommand):
    help = 'Load all WC2026 group stage teams (48) and matches (72) with correct data'

    def handle(self, *args, **kwargs):
        self.stdout.write("Loading national teams...")
        team_map = {}
        for name, code, group, flag in TEAMS:
            t, created = NationalTeam.objects.update_or_create(
                code=code,
                defaults={'name': name, 'group': group, 'flag': flag}
            )
            team_map[name] = t
            if created:
                self.stdout.write(f"  {flag}  {name} ({code}) — Group {group}")

        self.stdout.write("\nLoading group stage matches...")
        created_count = 0
        skipped_count = 0
        for home, away, phase, date_str in MATCHES:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            _, created = Match.objects.get_or_create(
                home_team=team_map[home],
                away_team=team_map[away],
                phase=phase,
                defaults={'kickoff': dt}
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ {len(TEAMS)} teams | {created_count} matches created | {skipped_count} already existed"
        ))
