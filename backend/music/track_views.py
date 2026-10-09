import random
import secrets
from functools import partial
from typing import cast

import httpx
from django.contrib.sessions.backends.base import SessionBase
from django.db import transaction
from django.shortcuts import get_object_or_404
from gameplay.models import GameTurn
from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from games.realtime import broadcast_game_event
from games.serializers import (
    GameTurnSerializer,
    HostTrackSerializer,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from spotify.services import (
    SpotifyNotConnectedError,
    SpotifyServiceError,
    get_valid_access_token,
)

from music.models import Track


class PrepareRandomTrackView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        session = cast(
            SessionBase,
            request.session,
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)
        except SpotifyNotConnectedError:
            return Response(
                {"detail": ("Connect Spotify before selecting a track.")},
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
                    "genre",
                    "team",
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

            if turn.status != GameTurn.Status.GENRE_SELECTED:
                return Response(
                    {"detail": ("A genre must be selected before preparing a track.")},
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

            playlist_id = genre.spotify_playlist_id.strip()

            if not playlist_id:
                return Response(
                    {"detail": (f"{genre.name} does not have a Spotify playlist.")},
                    status=status.HTTP_409_CONFLICT,
                )

            used_track_ids = set(
                GameTurn.objects.filter(
                    game=game,
                    track__isnull=False,
                ).values_list(
                    "track__spotify_track_id",
                    flat=True,
                )
            )

            headers = {
                "Authorization": f"Bearer {access_token}",
            }

            playlist_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/items"

            try:
                total_response = httpx.get(
                    playlist_url,
                    headers=headers,
                    params={
                        "fields": "total",
                    },
                    timeout=15.0,
                )
                total_response.raise_for_status()

                total_response_data = cast(
                    dict[str, object],
                    total_response.json(),
                )

                total = int(cast(int, total_response_data.get("total", 0)))
            except (
                httpx.HTTPError,
                TypeError,
                ValueError,
            ):
                return Response(
                    {"detail": ("Spotify could not read this genre playlist.")},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if total == 0:
                return Response(
                    {
                        "detail": "The Spotify playlist is empty.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            page_size = min(50, total)
            maximum_offset = max(0, total - page_size)

            offsets = {0}

            while len(offsets) < min(
                4,
                maximum_offset + 1,
            ):
                offsets.add(
                    random.SystemRandom().randint(
                        0,
                        maximum_offset,
                    )
                )

            candidates: list[dict[str, object]] = []

            try:
                for offset in offsets:
                    playlist_response = httpx.get(
                        playlist_url,
                        headers=headers,
                        params={
                            "limit": page_size,
                            "offset": offset,
                            "market": "from_token",
                        },
                        timeout=15.0,
                    )
                    playlist_response.raise_for_status()

                    response_data = cast(
                        dict[str, object],
                        playlist_response.json(),
                    )

                    items = cast(
                        list[dict[str, object]],
                        response_data.get(
                            "items",
                            [],
                        ),
                    )

                    for playlist_item in items:
                        if playlist_item.get("is_local") is True:
                            continue

                        spotify_item = playlist_item.get("item")

                        # Compatibility with Spotify's older
                        # playlist response format.
                        if spotify_item is None:
                            spotify_item = playlist_item.get("track")

                        if not isinstance(spotify_item, dict):
                            continue

                        if spotify_item.get("type") != "track":
                            continue

                        spotify_track_id = spotify_item.get("id")
                        spotify_uri = spotify_item.get("uri")
                        duration_ms = spotify_item.get("duration_ms")

                        if not isinstance(spotify_track_id, str):
                            continue

                        if not isinstance(spotify_uri, str):
                            continue

                        if not isinstance(duration_ms, int):
                            continue

                        if duration_ms < 10_000:
                            continue

                        if spotify_track_id in used_track_ids:
                            continue

                        is_explicit = bool(
                            spotify_item.get(
                                "explicit",
                                False,
                            )
                        )

                        if genre.exclude_explicit and is_explicit:
                            continue

                        if spotify_item.get("is_playable") is False:
                            continue

                        candidates.append(spotify_item)

            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    return Response(
                        {"detail": ("Spotify rate limit reached. Try again later.")},
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                return Response(
                    {"detail": ("Spotify could not load playlist tracks.")},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            except httpx.HTTPError:
                return Response(
                    {
                        "detail": STRING_ERROR_RESPONSES["spotify_could_not_be_reached"],
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if not candidates:
                return Response(
                    {
                        "detail": (
                            "No eligible unused tracks were found in this playlist."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            selected = secrets.SystemRandom().choice(candidates)

            album_data = selected.get("album")
            album = album_data if isinstance(album_data, dict) else {}

            artists_data = selected.get("artists")
            artists = artists_data if isinstance(artists_data, list) else []

            artist_names = [
                artist["name"]
                for artist in artists
                if (isinstance(artist, dict) and isinstance(artist.get("name"), str))
            ]

            images_data = album.get("images")
            images = images_data if isinstance(images_data, list) else []

            artwork_url = ""

            if images and isinstance(images[0], dict):
                image_url = images[0].get("url")

                if isinstance(image_url, str):
                    artwork_url = image_url

            spotify_track_id = cast(
                str,
                selected["id"],
            )
            spotify_uri = cast(
                str,
                selected["uri"],
            )
            title = cast(
                str,
                selected.get(
                    "name",
                    "Unknown title",
                ),
            )
            duration_ms = cast(
                int,
                selected["duration_ms"],
            )

            track, _ = Track.objects.update_or_create(
                spotify_track_id=spotify_track_id,
                defaults={
                    "spotify_uri": spotify_uri,
                    "title": title,
                    "artist": (", ".join(artist_names) or "Unknown artist"),
                    "album": str(
                        album.get(
                            "name",
                            "",
                        )
                    ),
                    "artwork_url": artwork_url,
                    "duration_ms": duration_ms,
                    "is_explicit": bool(
                        selected.get(
                            "explicit",
                            False,
                        )
                    ),
                },
            )

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                track=track,
                playback_start_ms=0,
                status=GameTurn.Status.TRACK_READY,
            )

            updated_turn = GameTurn.objects.select_related(
                "team",
                "genre",
                "track",
            ).get(pk=turn.pk)

            # This payload deliberately excludes all track information.
            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "track_ready": True,
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

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "track.ready",
                    event_data,
                )
            )

        return Response(
            {
                "turn": GameTurnSerializer(updated_turn).data,
                # This response is only returned to the authenticated host.
                "track": HostTrackSerializer(track).data,
            },
            status=status.HTTP_200_OK,
        )


