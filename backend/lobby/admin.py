from django.contrib import admin

from .models import LeaderVote, Player, Team


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
    readonly_fields = ("id", "joined_at", "last_seen_at")


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


