import hashlib
import random
import secrets
import time
from datetime import timedelta
from functools import partial
from typing import cast
from urllib.parse import urlencode
from uuid import UUID

import httpx
from celery import Task
from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from gameplay.models import GameTurn, ScoreEvent
from lobby.models import LeaderVote, Player, Team
from music.models import Genre, Track
from games.realtime import broadcast_game_event
from games.serializers import (
    AwardScoreSerializer,
    GameRoundsPerTeamUpdateSerializer,
    GameSerializer,
    GameTurnSerializer,
    GenreSerializer,
    HostTrackSerializer,
    LeaderVoteSubmitSerializer,
    PlayerJoinSerializer,
    PlayerSessionSerializer,
    PublicGameSerializer,
    PublicPlayerSerializer,
    ScoreEventSerializer,
    SpotifyDeviceSelectionSerializer,
    TeamSerializer,
)
from spotify.services import (
    SpotifyNotConnectedError,
    SpotifyServiceError,
    get_valid_access_token,
)
from spotify.tasks import stop_spotify_playback

class SpotifyLoginView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        state = secrets.token_urlsafe(32)
        request.session["spotify_oauth_state"] = state

        scopes = (
            "streaming",
            "user-read-email",
            "user-read-private",
            "user-read-playback-state",
            "user-modify-playback-state",
        )

        parameters = {
            "client_id": settings.SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
            "state": state,
            "scope": " ".join(scopes),
        }

        authorization_url = "https://accounts.spotify.com/authorize?" + urlencode(
            parameters
        )

        return HttpResponseRedirect(authorization_url)


class SpotifyCallbackView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        spotify_error = request.query_params.get("error")

        if spotify_error:
            return Response(
                {
                    "detail": ("Spotify authorization was denied or failed."),
                    "spotify_error": spotify_error,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = request.query_params.get("code")
        returned_state = request.query_params.get("state")
        expected_state = request.session.pop(
            "spotify_oauth_state",
            None,
        )

        if (
            not code
            or not returned_state
            or not expected_state
            or not secrets.compare_digest(
                returned_state,
                expected_state,
            )
        ):
            return Response(
                {"detail": "Invalid Spotify authorization state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_response = httpx.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
                },
                auth=(
                    settings.SPOTIFY_CLIENT_ID,
                    settings.SPOTIFY_CLIENT_SECRET,
                ),
                headers={"Content-Type": ("application/x-www-form-urlencoded")},
                timeout=15.0,
            )
            token_response.raise_for_status()
        except httpx.HTTPError:
            return Response(
                {"detail": "Spotify token exchange failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        token_data = token_response.json()

        request.session["spotify_tokens"] = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": (
                int(time.time()) + int(cast(int, token_data.get("expires_in", 3600)))
            ),
        }

        request.session.modified = True

        return_to = request.session.pop(
            "spotify_oauth_return_to",
            None,
        )

        if isinstance(return_to, str) and url_has_allowed_host_and_scheme(
            return_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return HttpResponseRedirect(return_to)

        return Response(
            {
                "connected": True,
                "detail": "Spotify connected successfully.",
            },
            status=status.HTTP_200_OK,
        )


class SpotifyStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        session = cast(
            SessionBase,
            request.session,
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)

            profile_response = httpx.get(
                "https://api.spotify.com/v1/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=15.0,
            )
            profile_response.raise_for_status()
        except SpotifyNotConnectedError:
            return Response(
                {
                    "connected": False,
                    "detail": STRING_ERROR_RESPONSES[
                        "spotify_not_connected_error_message"
                    ],
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (SpotifyServiceError, httpx.HTTPError):
            return Response(
                {
                    "connected": False,
                    "detail": STRING_ERROR_RESPONSES["spotify_could_not_be_reached"],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        profile = profile_response.json()
        is_premium = profile.get("product") == "premium"

        return Response(
            {
                "connected": True,
                "premium": is_premium,
                "display_name": profile.get("display_name"),
                "country": profile.get("country"),
                "spotify_user_id": profile.get("id"),
                "playback_available": is_premium,
            },
            status=status.HTTP_200_OK,
        )


class SpotifyDeviceListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        session = cast(
            SessionBase,
            request.session,
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)

            spotify_response = httpx.get(
                "https://api.spotify.com/v1/me/player/devices",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=15.0,
            )
            spotify_response.raise_for_status()
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": STRING_ERROR_RESPONSES[
                        "spotify_not_connected_error_message"
                    ]
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (SpotifyServiceError, httpx.HTTPError):
            return Response(
                {"detail": "Spotify devices could not be loaded."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_data = cast(
            dict[str, object],
            spotify_response.json(),
        )
        raw_devices = response_data.get("devices", [])
        devices = raw_devices if isinstance(raw_devices, list) else []

        available_devices = [
            {
                "id": device.get("id"),
                "name": device.get("name"),
                "type": device.get("type"),
                "is_active": device.get("is_active", False),
                "is_restricted": device.get(
                    "is_restricted",
                    False,
                ),
                "volume_percent": device.get("volume_percent"),
                "supports_volume": device.get(
                    "supports_volume",
                    False,
                ),
            }
            for device in devices
            if isinstance(device, dict) and isinstance(device.get("id"), str)
        ]

        return Response(
            {"devices": available_devices},
            status=status.HTTP_200_OK,
        )


class SelectSpotifyDeviceView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        serializer = SpotifyDeviceSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = cast(
            dict[str, str],
            serializer.validated_data,
        )
        requested_device_id = validated_data["device_id"]

        session = cast(
            SessionBase,
            request.session,
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)

            devices_response = httpx.get(
                "https://api.spotify.com/v1/me/player/devices",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=15.0,
            )
            devices_response.raise_for_status()
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": STRING_ERROR_RESPONSES[
                        "spotify_not_connected_error_message"
                    ]
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (SpotifyServiceError, httpx.HTTPError):
            return Response(
                {"detail": "Spotify devices could not be loaded."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_data = cast(
            dict[str, object],
            devices_response.json(),
        )
        raw_devices = response_data.get("devices", [])
        devices = raw_devices if isinstance(raw_devices, list) else []

        selected_device: dict[str, object] | None = None

        for device in devices:
            if isinstance(device, dict) and device.get("id") == requested_device_id:
                selected_device = device
                break

        if selected_device is None:
            return Response(
                {"device_id": ["This Spotify device is not currently available."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if selected_device.get("is_restricted") is True:
            return Response(
                {"device_id": ["Spotify does not permit API control of this device."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device_name = selected_device.get("name")
        safe_device_name = (
            device_name if isinstance(device_name, str) else "Spotify device"
        )

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
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 403:
                return Response(
                    {
                        "detail": (
                            "Spotify could not control this device. "
                            "Confirm that the account has Premium."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return Response(
                {"detail": "Spotify could not select this device."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except httpx.HTTPError:
            return Response(
                {"detail": STRING_ERROR_RESPONSES["spotify_could_not_be_reached"]},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        game = get_object_or_404(
            Game,
            pk=game_id,
            host=request.user,
        )

        Game.objects.filter(pk=game.pk).update(
            spotify_device_id=requested_device_id,
            spotify_device_name=safe_device_name,
        )

        return Response(
            {
                "selected": True,
                "device": {
                    "id": requested_device_id,
                    "name": safe_device_name,
                    "type": selected_device.get("type"),
                    "is_active": selected_device.get(
                        "is_active",
                        False,
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )


