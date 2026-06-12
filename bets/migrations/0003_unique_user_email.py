from django.db import migrations


class Migration(migrations.Migration):
    """Enforce email uniqueness on auth_user at the database level."""
    dependencies = [
        ('bets', '0002_seed_sweepstake_teams'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_unique ON auth_user (LOWER(email)) WHERE email != '';",
            reverse_sql="DROP INDEX IF EXISTS auth_user_email_unique;",
        ),
    ]
