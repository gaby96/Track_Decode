from django.contrib import admin

from .models import GameTurn, ScoreEvent


@admin.register(GameTurn)
class GameTurnAdmin(admin.ModelAdmin):
    list_display = (
        "game",
        "round_number",
        "turn_position",
        "team",
        "genre",
        "track",
        "status",
    )
    list_filter = ("game", "round_number", "status", "genre")
    search_fields = ("game__name", "team__name", "genre__name")
    autocomplete_fields = ("game", "team", "genre", "track")
    readonly_fields = ("id", "created_at")


@admin.register(ScoreEvent)
class ScoreEventAdmin(admin.ModelAdmin):
    list_display = (
        "game",
        "team",
        "turn",
        "song_title_correct",
        "artist_correct",
        "points",
        "awarded_by",
        "created_at",
    )
    list_filter = (
        "game",
        "team",
        "song_title_correct",
        "artist_correct",
        "points",
    )
    search_fields = (
        "game__name",
        "team__name",
        "awarded_by__username",
    )
    autocomplete_fields = (
        "game",
        "turn",
        "team",
        "awarded_by",
    )
    readonly_fields = (
        "id",
        "created_at",
    )


