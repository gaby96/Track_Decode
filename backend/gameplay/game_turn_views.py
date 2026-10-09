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

PLAYBACK_CLIP_DURATION_SECONDS = 15


def _find_replacement_spotify_device(
    *,
    access_token: str,
    saved_device_id: str,
    saved_device_name: str,
) -> dict[str, object] | None:
    normalized_name = saved_device_name.strip()

    if not normalized_name:
        return None

    devices_response = httpx.get(
        "https://api.spotify.com/v1/me/player/devices",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=15.0,
    )
    devices_response.raise_for_status()

    response_data = cast(
        dict[str, object],
        devices_response.json(),
    )
    raw_devices = response_data.get("devices", [])
    devices = raw_devices if isinstance(raw_devices, list) else []

    matching_devices = [
        device
        for device in devices
        if (
            isinstance(device, dict)
            and isinstance(device.get("id"), str)
            and device.get("id") != saved_device_id
            and device.get("name") == normalized_name
            and device.get("is_restricted") is not True
        )
    ]

    if not matching_devices:
        return None

    active_match = next(
        (device for device in matching_devices if device.get("is_active") is True),
        None,
    )

    return active_match or matching_devices[0]


class StartTrackPlaybackView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        session = cast(
            SessionBase,
            request.session,
        )

        # The Celery worker needs this key to retrieve the host's
        # Spotify tokens from Django's database-backed session.
        if session.session_key is None:
            session.save()

        session_key = session.session_key

        if session_key is None:
            return Response(
                {
                    "detail": "The host session could not be saved.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": STRING_ERROR_RESPONSES[
                        "spotify_not_connected_error_message"
                    ],
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except SpotifyServiceError:
            return Response(
                {
                    "detail": "Spotify authentication failed.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "track",
                    "team",
                    "genre",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": STRING_ERROR_RESPONSES["game_not_in_progress"],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status not in (
                GameTurn.Status.TRACK_READY,
                GameTurn.Status.AWAITING_ANSWER,
            ):
                return Response(
                    {
                        "detail": (
                            "A prepared track can only be played "
                            "before the answer is revealed."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            track = turn.track

            if track is None:
                return Response(
                    {"detail": ("This turn does not have a prepared track.")},
                    status=status.HTTP_409_CONFLICT,
                )

            genre = turn.genre

            if genre is None:
                return Response(
                    {
                        "detail": "This turn does not have a genre.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            device_id = game.spotify_device_id.strip()

            if not device_id:
                return Response(
                    {"detail": ("Select a central Spotify device before playback.")},
                    status=status.HTTP_409_CONFLICT,
                )

            playback_start_ms = int(game.default_playback_start_ms)

            def attempt_playback(target_device_id: str) -> None:
                spotify_response = httpx.put(
                    "https://api.spotify.com/v1/me/player/play",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    params={
                        "device_id": target_device_id,
                    },
                    json={
                        "uris": [track.spotify_uri],
                        "position_ms": playback_start_ms,
                    },
                    timeout=15.0,
                )
                spotify_response.raise_for_status()

            try:
                attempt_playback(device_id)

            except httpx.HTTPStatusError as error:
                spotify_status = error.response.status_code

                if spotify_status == 404:
                    try:
                        replacement_device = _find_replacement_spotify_device(
                            access_token=access_token,
                            saved_device_id=device_id,
                            saved_device_name=game.spotify_device_name,
                        )
                    except httpx.HTTPError:
                        replacement_device = None

                    if replacement_device is None:
                        return Response(
                            {
                                "detail": (
                                    "The selected Spotify device is "
                                    "unavailable. Open Spotify and select "
                                    "the device again."
                                )
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    replacement_device_id = cast(
                        str,
                        replacement_device["id"],
                    )
                    replacement_device_name = cast(
                        str,
                        replacement_device.get("name") or game.spotify_device_name,
                    )

                    try:
                        attempt_playback(replacement_device_id)
                    except httpx.HTTPStatusError as retry_error:
                        retry_status = retry_error.response.status_code

                        if retry_status == 403:
                            return Response(
                                {
                                    "detail": (
                                        "Spotify refused playback. Confirm "
                                        "that the account has Premium and the "
                                        "device is not restricted."
                                    )
                                },
                                status=status.HTTP_403_FORBIDDEN,
                            )

                        if retry_status == 429:
                            return Response(
                                {
                                    "detail": (
                                        "Spotify's rate limit was reached. "
                                        "Try again shortly."
                                    )
                                },
                                status=status.HTTP_429_TOO_MANY_REQUESTS,
                            )

                        return Response(
                            {
                                "detail": (
                                    "The selected Spotify device is "
                                    "unavailable. Open Spotify and select "
                                    "the device again."
                                )
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    except httpx.HTTPError:
                        return Response(
                            {
                                "detail": STRING_ERROR_RESPONSES["spotify_could_not_be_reached"],
                            },
                            status=status.HTTP_502_BAD_GATEWAY,
                        )

                    device_id = replacement_device_id
                    game.spotify_device_id = replacement_device_id
                    game.spotify_device_name = replacement_device_name
                    game.save(
                        update_fields=[
                            "spotify_device_id",
                            "spotify_device_name",
                        ]
                    )

                elif spotify_status == 403:
                    return Response(
                        {
                            "detail": (
                                "Spotify refused playback. Confirm "
                                "that the account has Premium and the "
                                "device is not restricted."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                elif spotify_status == 429:
                    return Response(
                        {
                            "detail": (
                                "Spotify's rate limit was reached. Try again shortly."
                            )
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                else:
                    return Response(
                        {
                            "detail": "Spotify could not start playback.",
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            except httpx.HTTPError:
                return Response(
                    {
                        "detail": STRING_ERROR_RESPONSES["spotify_could_not_be_reached"],
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            playback_started_at = timezone.now()
            clip_ends_at = playback_started_at + timedelta(
                seconds=PLAYBACK_CLIP_DURATION_SECONDS
            )

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                status=GameTurn.Status.PLAYING,
                playback_started_at=playback_started_at,
                playback_stopped_at=None,
            )

            updated_turn = GameTurn.objects.select_related(
                "track",
                "team",
                "genre",
            ).get(pk=turn.pk)

            playback_event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "playback_duration_seconds": PLAYBACK_CLIP_DURATION_SECONDS,
                "playback_started_at": (playback_started_at.isoformat()),
                "clip_ends_at": clip_ends_at.isoformat(),
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
                },
                "genre": {
                    "id": str(genre.pk),
                    "name": genre.name,
                    "color": genre.color,
                },
            }

            pause_task = cast(
                Task,
                stop_spotify_playback,
            )

            # Register this first because stopping Spotify after the clip
            # duration is more important than sending the WebSocket event.
            transaction.on_commit(
                lambda: pause_task.apply_async(
                    args=(
                        str(turn.pk),
                        session_key,
                    ),
                    countdown=PLAYBACK_CLIP_DURATION_SECONDS,
                )
            )

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "playback.started",
                    playback_event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "started": True,
                "clip_duration_seconds": PLAYBACK_CLIP_DURATION_SECONDS,
                "playback_started_at": playback_started_at,
                "clip_ends_at": clip_ends_at,
                "device": {
                    "id": device_id,
                    "name": game.spotify_device_name,
                },
                "turn": GameTurnSerializer(updated_turn).data,
                # Only the authenticated host receives the answer.
                "track": HostTrackSerializer(track).data,
            },
            status=status.HTTP_200_OK,
        )


class StopTrackPlaybackView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(
        self,
        request,
        game_id,
        turn_id,
    ):
        session = cast(
            SessionBase,
            request.session,
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": STRING_ERROR_RESPONSES[
                        "spotify_not_connected_error_message"
                    ],
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except SpotifyServiceError:
            return Response(
                {
                    "detail": "Spotify authentication failed.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "team",
                    "genre",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": STRING_ERROR_RESPONSES["game_not_in_progress"],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status != GameTurn.Status.PLAYING:
                return Response(
                    {"detail": ("This turn is not currently playing.")},
                    status=status.HTTP_409_CONFLICT,
                )

            device_id = game.spotify_device_id.strip()

            if not device_id:
                return Response(
                    {"detail": ("No central Spotify device has been selected.")},
                    status=status.HTTP_409_CONFLICT,
                )

            try:
                spotify_response = httpx.put(
                    "https://api.spotify.com/v1/me/player/pause",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                    params={
                        "device_id": device_id,
                    },
                    timeout=15.0,
                )
                spotify_response.raise_for_status()

            except httpx.HTTPStatusError as error:
                spotify_status = error.response.status_code

                if spotify_status == 404:
                    return Response(
                        {
                            "detail": (
                                "The selected Spotify device is "
                                "unavailable or there is no active "
                                "playback."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if spotify_status == 403:
                    return Response(
                        {
                            "detail": (
                                "Spotify refused the pause request. "
                                "Confirm that the account has Premium."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if spotify_status == 429:
                    return Response(
                        {
                            "detail": (
                                "Spotify's rate limit was reached. Try again shortly."
                            )
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                return Response(
                    {"detail": ("Spotify could not stop playback.")},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            except httpx.HTTPError:
                return Response(
                    {
                        "detail": STRING_ERROR_RESPONSES["spotify_could_not_be_reached"],
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            playback_stopped_at = timezone.now()

            updated_count = GameTurn.objects.filter(
                pk=turn.pk,
                status=GameTurn.Status.PLAYING,
            ).update(
                status=GameTurn.Status.AWAITING_ANSWER,
                playback_stopped_at=playback_stopped_at,
            )

            # The Celery task might have stopped this turn while
            # the manual stop request was being processed.
            if updated_count == 0:
                return Response(
                    {"detail": ("This turn is no longer playing.")},
                    status=status.HTTP_409_CONFLICT,
                )

            updated_turn = GameTurn.objects.select_related(
                "team",
                "genre",
            ).get(pk=turn.pk)

            genre = updated_turn.genre

            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "reason": "admin_manual",
                "playback_stopped_at": (playback_stopped_at.isoformat()),
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
                },
                "genre": (
                    {
                        "id": str(genre.pk),
                        "name": genre.name,
                        "color": genre.color,
                    }
                    if genre is not None
                    else None
                ),
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "playback.stopped",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "stopped": True,
                "reason": "admin_manual",
                "playback_stopped_at": playback_stopped_at,
                "turn": GameTurnSerializer(updated_turn).data,
            },
            status=status.HTTP_200_OK,
        )


class RevealAnswerView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "track",
                    "team",
                    "genre",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {"detail": STRING_ERROR_RESPONSES["game_not_in_progress"]},
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status == GameTurn.Status.ANSWER_REVEALED:
                track = turn.track

                if track is None:
                    return Response(
                        {"detail": "This turn does not have a track."},
                        status=status.HTTP_409_CONFLICT,
                    )

                return Response(
                    {
                        "revealed": True,
                        "detail": "The answer has already been revealed.",
                        "turn": GameTurnSerializer(turn).data,
                        "answer": HostTrackSerializer(track).data,
                    },
                    status=status.HTTP_200_OK,
                )

            if turn.status != GameTurn.Status.AWAITING_ANSWER:
                return Response(
                    {
                        "detail": (
                            "Playback must stop before the answer can be revealed."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            track = turn.track

            if track is None:
                return Response(
                    {"detail": "This turn does not have a track."},
                    status=status.HTTP_409_CONFLICT,
                )

            answer_revealed_at = timezone.now()

            GameTurn.objects.filter(pk=turn.pk).update(
                status=GameTurn.Status.ANSWER_REVEALED,
                answer_revealed_at=answer_revealed_at,
            )

            updated_turn = GameTurn.objects.select_related(
                "track",
                "team",
                "genre",
            ).get(pk=turn.pk)

            track = updated_turn.track

            if track is None:
                return Response(
                    {
                        "detail": "This turn does not have a track.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            genre = updated_turn.genre

            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "answer_revealed_at": answer_revealed_at.isoformat(),
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
                },
                "genre": (
                    {
                        "id": str(genre.pk),
                        "name": genre.name,
                        "color": genre.color,
                    }
                    if genre is not None
                    else None
                ),
                "answer": {
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "artwork_url": track.artwork_url,
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "answer.revealed",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "revealed": True,
                "answer_revealed_at": answer_revealed_at,
                "turn": GameTurnSerializer(updated_turn).data,
                "answer": HostTrackSerializer(track).data,
            },
            status=status.HTTP_200_OK,
        )


class AdvanceTurnView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            completed_turn = get_object_or_404(
                GameTurn.objects.select_for_update(),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": STRING_ERROR_RESPONSES["game_not_in_progress"],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if completed_turn.status != GameTurn.Status.COMPLETED:
                return Response(
                    {
                        "detail": (
                            "The current turn must be completed before advancing."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if GameTurn.objects.filter(
                game=game,
                status=GameTurn.Status.ACTIVE,
            ).exists():
                return Response(
                    {
                        "detail": "Another turn is already active.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            next_turn = (
                GameTurn.objects.select_for_update()
                .filter(
                    game=game,
                    round_number=completed_turn.round_number,
                    turn_position__gt=(completed_turn.turn_position),
                    status=GameTurn.Status.WAITING,
                )
                .order_by("turn_position")
                .first()
            )

            if next_turn is None:
                round_event_data = {
                    "game_id": str(game.pk),
                    "round_number": (completed_turn.round_number),
                    "round_completed": True,
                    "completed_turn_id": str(completed_turn.pk),
                }

                transaction.on_commit(
                    partial(
                        broadcast_game_event,
                        game.join_token,
                        "round.completed",
                        round_event_data,
                    ),
                    robust=True,
                )

                return Response(
                    {
                        "advanced": False,
                        "round_completed": True,
                        "round_number": (completed_turn.round_number),
                        "detail": ("Every team has completed this round."),
                        "next_turn": None,
                    },
                    status=status.HTTP_200_OK,
                )

            started_at = timezone.now()

            GameTurn.objects.filter(
                pk=next_turn.pk,
            ).update(
                status=GameTurn.Status.ACTIVE,
                started_at=started_at,
            )

            updated_turn = GameTurn.objects.select_related(
                "team",
                "genre",
                "track",
            ).get(pk=next_turn.pk)

            turn_event_data = {
                "game_id": str(game.pk),
                "previous_turn_id": str(completed_turn.pk),
                "round_number": (updated_turn.round_number),
                "active_turn": {
                    "id": str(updated_turn.pk),
                    "round_number": (updated_turn.round_number),
                    "turn_position": (updated_turn.turn_position),
                    "status": updated_turn.status,
                    "started_at": started_at.isoformat(),
                    "team": {
                        "id": str(updated_turn.team.pk),
                        "name": updated_turn.team.name,
                        "color": updated_turn.team.color,
                    },
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "turn.advanced",
                    turn_event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "advanced": True,
                "round_completed": False,
                "active_turn": GameTurnSerializer(updated_turn).data,
            },
            status=status.HTTP_200_OK,
        )


