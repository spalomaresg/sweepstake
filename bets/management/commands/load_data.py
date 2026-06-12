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

# All 48 matches — UTC times derived from official ET/BST sources
# ET = UTC-4 in summer. BST = UTC+1.
# Match (home, away, group, "YYYY-MM-DD HH:MM" UTC)
MATCHES = [
    # ── GROUP A ──────────────────────────────────────────────────────────────
    ("Mexico",       "South Africa",        "group_stage", "2026-06-11 19:00"),  # 3pm ET
    ("South Korea",  "Czechia",             "group_stage", "2026-06-12 02:00"),  # 10pm ET Jun 11
    ("Czechia",      "South Africa",        "group_stage", "2026-06-18 16:00"),  # 12pm ET
    ("Mexico",       "South Korea",         "group_stage", "2026-06-19 01:00"),  # 9pm ET Jun 18
    ("Mexico",       "Czechia",             "group_stage", "2026-06-25 01:00"),  # 9pm ET Jun 24
    ("South Africa", "South Korea",         "group_stage", "2026-06-25 01:00"),  # 9pm ET Jun 24

    # ── GROUP B ──────────────────────────────────────────────────────────────
    ("Canada",       "Bosnia & Herzegovina","group_stage", "2026-06-12 19:00"),  # 3pm ET
    ("Switzerland",  "Qatar",               "group_stage", "2026-06-13 02:00"),  # 10pm ET Jun 12
    ("Bosnia & Herzegovina","Qatar",         "group_stage", "2026-06-19 16:00"),
    ("Switzerland",  "Canada",              "group_stage", "2026-06-20 01:00"),
    ("Switzerland",  "Bosnia & Herzegovina","group_stage", "2026-06-26 01:00"),
    ("Canada",       "Qatar",               "group_stage", "2026-06-26 01:00"),

    # ── GROUP C ──────────────────────────────────────────────────────────────
    ("Brazil",       "Morocco",             "group_stage", "2026-06-13 19:00"),  # 3pm ET
    ("Haiti",        "Scotland",            "group_stage", "2026-06-14 02:00"),  # 10pm ET Jun 13
    ("Morocco",      "Scotland",            "group_stage", "2026-06-20 16:00"),
    ("Brazil",       "Haiti",               "group_stage", "2026-06-21 01:00"),
    ("Brazil",       "Scotland",            "group_stage", "2026-06-27 01:00"),
    ("Morocco",      "Haiti",               "group_stage", "2026-06-27 01:00"),

    # ── GROUP D ──────────────────────────────────────────────────────────────
    ("USA",          "Paraguay",            "group_stage", "2026-06-13 01:00"),  # 9pm ET Jun 12
    ("Australia",    "Turkey",              "group_stage", "2026-06-14 09:00"),  # 5am ET — west coast late slot
    ("Turkey",       "Paraguay",            "group_stage", "2026-06-20 19:00"),
    ("USA",          "Australia",           "group_stage", "2026-06-19 19:00"),
    ("USA",          "Turkey",              "group_stage", "2026-06-25 01:00"),  # sync Jun 24
    ("Australia",    "Paraguay",            "group_stage", "2026-06-25 01:00"),

    # ── GROUP E ──────────────────────────────────────────────────────────────
    ("Germany",      "Curacao",             "group_stage", "2026-06-15 19:00"),
    ("Ecuador",      "Ivory Coast",         "group_stage", "2026-06-16 02:00"),
    ("Germany",      "Ecuador",             "group_stage", "2026-06-22 01:00"),
    ("Ivory Coast",  "Curacao",             "group_stage", "2026-06-21 19:00"),
    ("Germany",      "Ivory Coast",         "group_stage", "2026-06-26 21:30"),  # sync
    ("Ecuador",      "Curacao",             "group_stage", "2026-06-26 21:30"),

    # ── GROUP F ──────────────────────────────────────────────────────────────
    ("Netherlands",  "Japan",               "group_stage", "2026-06-14 22:00"),
    ("Sweden",       "Tunisia",             "group_stage", "2026-06-15 02:00"),
    ("Netherlands",  "Sweden",              "group_stage", "2026-06-21 22:00"),
    ("Japan",        "Tunisia",             "group_stage", "2026-06-22 01:00"),
    ("Netherlands",  "Tunisia",             "group_stage", "2026-06-27 01:00"),  # sync
    ("Japan",        "Sweden",              "group_stage", "2026-06-27 01:00"),

    # ── GROUP G ──────────────────────────────────────────────────────────────
    ("Belgium",      "Egypt",               "group_stage", "2026-06-15 22:00"),
    ("Iran",         "New Zealand",         "group_stage", "2026-06-16 01:00"),
    ("Belgium",      "Iran",                "group_stage", "2026-06-20 22:00"),
    ("Egypt",        "New Zealand",         "group_stage", "2026-06-21 01:00"),
    ("Belgium",      "New Zealand",         "group_stage", "2026-06-26 01:00"),  # sync
    ("Iran",         "Egypt",               "group_stage", "2026-06-26 01:00"),

    # ── GROUP H ──────────────────────────────────────────────────────────────
    ("Spain",        "Cape Verde",          "group_stage", "2026-06-15 16:00"),  # 12pm ET
    ("Saudi Arabia", "Uruguay",             "group_stage", "2026-06-16 22:00"),
    ("Spain",        "Saudi Arabia",        "group_stage", "2026-06-21 17:00"),
    ("Cape Verde",   "Uruguay",             "group_stage", "2026-06-22 22:00"),
    ("Spain",        "Uruguay",             "group_stage", "2026-06-27 01:00"),  # sync
    ("Cape Verde",   "Saudi Arabia",        "group_stage", "2026-06-27 01:00"),

    # ── GROUP I ──────────────────────────────────────────────────────────────
    ("France",       "Senegal",             "group_stage", "2026-06-18 22:00"),
    ("Iraq",         "Norway",              "group_stage", "2026-06-19 01:00"),
    ("France",       "Iraq",                "group_stage", "2026-06-22 19:00"),
    ("Senegal",      "Norway",              "group_stage", "2026-06-24 22:00"),
    ("France",       "Norway",              "group_stage", "2026-06-27 21:30"),  # sync
    ("Senegal",      "Iraq",                "group_stage", "2026-06-27 21:30"),

    # ── GROUP J ──────────────────────────────────────────────────────────────
    ("Argentina",    "Algeria",             "group_stage", "2026-06-17 01:00"),
    ("Austria",      "Jordan",              "group_stage", "2026-06-17 22:00"),
    ("Argentina",    "Austria",             "group_stage", "2026-06-23 01:00"),
    ("Algeria",      "Jordan",              "group_stage", "2026-06-23 22:00"),
    ("Argentina",    "Jordan",              "group_stage", "2026-06-28 01:00"),  # sync
    ("Algeria",      "Austria",             "group_stage", "2026-06-28 01:00"),

    # ── GROUP K ──────────────────────────────────────────────────────────────
    ("Portugal",     "Uzbekistan",          "group_stage", "2026-06-18 01:00"),
    ("DR Congo",     "Colombia",            "group_stage", "2026-06-17 19:00"),
    ("Portugal",     "DR Congo",            "group_stage", "2026-06-24 01:00"),
    ("Uzbekistan",   "Colombia",            "group_stage", "2026-06-24 19:00"),
    ("Portugal",     "Colombia",            "group_stage", "2026-06-28 21:30"),  # sync
    ("DR Congo",     "Uzbekistan",          "group_stage", "2026-06-28 21:30"),

    # ── GROUP L ──────────────────────────────────────────────────────────────
    ("England",      "Croatia",             "group_stage", "2026-06-17 20:00"),  # 21:00 BST
    ("Ghana",        "Panama",              "group_stage", "2026-06-18 19:00"),
    ("England",      "Ghana",               "group_stage", "2026-06-23 20:00"),
    ("Croatia",      "Panama",              "group_stage", "2026-06-24 01:00"),
    ("England",      "Panama",              "group_stage", "2026-06-27 21:00"),  # 22:00 BST — sync
    ("Croatia",      "Ghana",               "group_stage", "2026-06-27 21:00"),
]


class Command(BaseCommand):
    help = 'Load all WC2026 group stage teams (48) and matches (48) with correct data'

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
