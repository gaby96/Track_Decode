from django.contrib import admin

from .models import (
    Game,
    GameTurn,
    Genre,
    LeaderVote,
    Player,
    ScoreEvent,
    Team,
    Track,
)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "join_code",
        "number_of_teams",
        "rounds_per_team",
        "default_playback_start_ms",
        "status",
        "registration_open",
        "host",
        "created_at",
    )
    list_filter = ("status", "registration_open", "created_at")
    search_fields = ("name", "join_code", "host__username")
    readonly_fields = (
        "id",
        "join_token",
        "join_code",
        "created_at",
        "updated_at",
        "finished_at",
    )


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "game",
        "position",
        "leader",
    )
    list_filter = ("game",)
    search_fields = ("name", "game__name")
    autocomplete_fields = ("game", "leader")


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "game",
        "team",
        "is_connected",
        "joined_at",
    )
    list_filter = ("game", "team", "is_connected")
    search_fields = ("display_name", "game__name")
    autocomplete_fields = ("game", "team")
    readonly_fields = ("id", "session_token_hash", "joined_at", "last_seen_at")


@admin.register(LeaderVote)
class LeaderVoteAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "voter",
        "candidate",
        "created_at",
    )
    list_filter = ("team__game", "team")
    search_fields = (
        "voter__display_name",
        "candidate__display_name",
        "team__name",
    )
    autocomplete_fields = ("team", "voter", "candidate")
    readonly_fields = ("created_at",)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "spotify_playlist_id",
        "is_enabled",
        "exclude_explicit",
        "created_at",
    )
    list_filter = ("is_enabled", "exclude_explicit")
    search_fields = ("name", "spotify_playlist_id")
    readonly_fields = ("id", "created_at")


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


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "artist",
        "album",
        "duration_ms",
        "is_explicit",
    )
    list_filter = ("is_explicit",)
    search_fields = (
        "title",
        "artist",
        "album",
        "spotify_track_id",
    )
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
