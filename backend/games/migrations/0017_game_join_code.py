import secrets

from django.db import migrations, models

import games.models


JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 6


def populate_join_codes(apps, schema_editor):
    Game = apps.get_model("games", "Game")
    existing_codes = set(
        Game.objects.exclude(join_code__isnull=True)
        .exclude(join_code="")
        .values_list("join_code", flat=True)
    )

    for game in Game.objects.filter(join_code__isnull=True):
        while True:
            join_code = "".join(
                secrets.choice(JOIN_CODE_ALPHABET)
                for _ in range(JOIN_CODE_LENGTH)
            )

            if join_code not in existing_codes:
                existing_codes.add(join_code)
                game.join_code = join_code
                game.save(update_fields=["join_code"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0016_game_finished_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="join_code",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=6,
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_join_codes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="game",
            name="join_code",
            field=models.CharField(
                default=games.models.generate_join_code,
                editable=False,
                max_length=6,
                unique=True,
            ),
        ),
    ]
