from django.contrib import admin

from .models import Genre, Track


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


