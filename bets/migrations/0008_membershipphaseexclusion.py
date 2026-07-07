from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bets', '0007_match_penalty_goals'),
    ]

    operations = [
        migrations.CreateModel(
            name='MembershipPhaseExclusion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phase', models.CharField(max_length=20, choices=[
                    ('group_stage', 'Group Stage'),
                    ('round_of_32', 'Round of 32'),
                    ('round_of_16', 'Round of 16'),
                    ('quarterfinals', 'Quarter-finals'),
                    ('semifinals', 'Semi-finals'),
                    ('third_place', 'Third Place'),
                    ('final', 'Final'),
                ])),
                ('membership', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='phase_exclusions',
                    to='bets.sweepstakemembership',
                )),
            ],
            options={
                'verbose_name': 'Phase Exclusion',
                'verbose_name_plural': 'Phase Exclusions',
                'ordering': ['membership__user__username', 'phase'],
                'unique_together': {('membership', 'phase')},
            },
        ),
    ]
