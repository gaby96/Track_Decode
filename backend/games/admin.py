from typing import cast

import httpx
from django.contrib import admin, messages
from django.contrib.sessions.backends.base import SessionBase
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

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
from .services.spotify import (
    SpotifyNotConnectedError,
    SpotifyServiceError,
    get_valid_access_token,
)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    change_form_template = "admin/games/game/change_form.html"
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

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/spotify/",
                self.admin_site.admin_view(self.spotify_devices_view),
                name="games_game_spotify",
            ),
            path(
                "<path:object_id>/spotify/connect/",
                self.admin_site.admin_view(self.spotify_connect_view),
                name="games_game_spotify_connect",
            ),
        ]
        return custom_urls + super().get_urls()

    def _get_changeable_game(self, request: HttpRequest, object_id: str) -> Game:
        game = self.get_object(request, object_id)

        if game is None:
            raise PermissionDenied

        if not self.has_change_permission(request, game):
            raise PermissionDenied

        return game

    def spotify_connect_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        game = self._get_changeable_game(request, object_id)
        request.session["spotify_oauth_return_to"] = reverse(
            "admin:games_game_spotify",
            args=(game.pk,),
        )
        request.session.modified = True
        return redirect("games:spotify-login")

    def spotify_devices_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        game = self._get_changeable_game(request, object_id)
        session = cast(SessionBase, request.session)
        devices: list[dict[str, object]] = []
        spotify_connected = False
        access_token: str | None = None
        try:
            
            raw_devices, spotify_connected, access_token = get_spotify_devices(request, session)
            if isinstance(raw_devices, list):
                devices = [
                    device
                    for device in raw_devices
                    if (isinstance(device, dict) and isinstance(device.get("id"), str))
                ]
        except SpotifyNotConnectedError:
            pass
        except (SpotifyServiceError, httpx.HTTPError):
            messages.error(
                request,
                "Spotify devices could not be loaded. Try reconnecting Spotify.",
            )

        if request.method == "POST":
            select_spotify_device(request,devices, game, access_token)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": game,
            "title": f"Select Spotify device for {game}",
            "devices": devices,
            "spotify_connected": spotify_connected,
            "current_device_id": game.spotify_device_id,
            "connect_url": reverse(
                "admin:games_game_spotify_connect",
                args=(game.pk,),
            ),
            "change_url": reverse(
                "admin:games_game_change",
                args=(game.pk,),
            ),
        }
        return TemplateResponse(
            request,
            "admin/games/game/spotify_devices.html",
            context,
        )

def get_spotify_devices(request, session):
    access_token: str = get_valid_access_token(
        session,
        user_id=request.user.pk,
    )
    spotify_connected = True
    devices_response = httpx.get(
        "https://api.spotify.com/v1/me/player/devices",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15.0,
    )
    devices_response.raise_for_status()
    response_data = cast(dict[str, object], devices_response.json())
    raw_devices = response_data.get("devices", [])

    return raw_devices, spotify_connected, access_token

def select_spotify_device(request, devices, game, access_token):
    requested_device_id = request.POST.get("device_id", "").strip()
    selected_device = next(
        (
            device
            for device in devices
            if device.get("id") == requested_device_id
        ),
        None,
    )
    
    if selected_device is None:
        messages.error(
            request,
            "Select a Spotify device that is currently available.",
        )
    elif selected_device.get("is_restricted") is True:
        messages.error(
            request,
            "Spotify does not permit API control of this device.",
        )
    else:
        try:
            transfer_response = httpx.put(
                "https://api.spotify.com/v1/me/player",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "device_ids": [requested_device_id],
                    "play": False,
                },
                timeout=15.0,
            )
            transfer_response.raise_for_status()
        except httpx.HTTPError:
            messages.error(
                request,
                "Spotify could not activate the selected device.",
            )
        else:
            device_name = selected_device.get("name")
            game.spotify_device_id = requested_device_id
            game.spotify_device_name = (
                device_name
                if isinstance(device_name, str)
                else "Spotify device"
            )
            game.save(
                update_fields=[
                    "spotify_device_id",
                    "spotify_device_name",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                f'Spotify device "{game.spotify_device_name}" selected.',
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:games_game_change",
                    args=(game.pk,),
                )
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
