from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bets', '0004_multi_sweepstake'),
    ]

    operations = [
        migrations.AlterField(
            model_name='match',
            name='phase',
            field=models.CharField(
                choices=[
                    ('group_stage', 'Group Stage'),
                    ('round_of_16', 'Round of 16'),
                    ('quarterfinals', 'Quarter-finals'),
                    ('semifinals', 'Semi-finals'),
                    ('third_place', 'Third Place'),
                    ('final', 'Final'),
                ],
                max_length=20,
            ),
        ),
    ]
