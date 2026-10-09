from django.db import migrations


MODEL_APP_LABELS = {
    "team": "lobby",
    "player": "lobby",
    "leadervote": "lobby",
    "gameturn": "gameplay",
    "scoreevent": "gameplay",
    "genre": "music",
    "track": "music",
}


def move_content_types(apps, schema_editor, labels=MODEL_APP_LABELS):
    content_type_model = apps.get_model("contenttypes", "ContentType")

    for model_name, target_app_label in labels.items():
        source = content_type_model.objects.filter(
            app_label="games",
            model=model_name,
        ).first()
        target = content_type_model.objects.filter(
            app_label=target_app_label,
            model=model_name,
        ).first()

        if source is None:
            continue

        # Preserve the original content-type ID for admin logs, permissions,
        # and any generic relations. A duplicate can exist if post_migrate
        # already created content types for the new app labels.
        if target is not None:
            target.delete()

        source.app_label = target_app_label
        source.save(update_fields=["app_label"])


def restore_content_types(apps, schema_editor):
    reverse_labels = {
        model_name: "games"
        for model_name in MODEL_APP_LABELS
    }
    content_type_model = apps.get_model("contenttypes", "ContentType")

    for model_name, target_app_label in reverse_labels.items():
        source_app_label = MODEL_APP_LABELS[model_name]
        source = content_type_model.objects.filter(
            app_label=source_app_label,
            model=model_name,
        ).first()
        target = content_type_model.objects.filter(
            app_label=target_app_label,
            model=model_name,
        ).first()

        if source is None:
            continue
        if target is not None:
            target.delete()

        source.app_label = target_app_label
        source.save(update_fields=["app_label"])


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("games", "0021_remove_gameturn_game_remove_gameturn_genre_and_more"),
        ("gameplay", "0001_initial"),
        ("lobby", "0001_initial"),
        ("music", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(move_content_types, restore_content_types),
    ]
