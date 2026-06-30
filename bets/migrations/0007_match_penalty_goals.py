from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bets', '0006_restore_round_of_32'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='penalty_home_goals',
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='match',
            name='penalty_away_goals',
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
