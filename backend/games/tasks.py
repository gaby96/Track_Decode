import logging

import httpx
from celery import shared_task
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

from .models import GameTurn
from .realtime import broadcast_game_event
from .services.spotify import (
    SpotifyNotConnectedError,
    SpotifyServiceError,
    get_valid_access_token,
)


logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def stop_spotify_playback(
    turn_id: str,
    session_key: str,
) -> None:
    turn = (
        GameTurn.objects.select_related(
            "game",
            "team",
            "genre",
        )
        .filter(pk=turn_id)
        .first()
    )

    if turn is None:
        return

    if turn.status != GameTurn.Status.PLAYING:
        return

    game = turn.game
    device_id = game.spotify_device_id.strip()

    if not device_id:
        return

    session = SessionStore(
        session_key=session_key,
    )

    try:
        access_token = get_valid_access_token(session)

        if session.modified:
            session.save()

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

    except (
        SpotifyNotConnectedError,
        SpotifyServiceError,
        httpx.HTTPError,
    ):
        logger.exception(
            "Spotify playback could not be stopped for turn %s.",
            turn_id,
        )
        return

    playback_stopped_at = timezone.now()

    updated_count = GameTurn.objects.filter(
        pk=turn.pk,
        status=GameTurn.Status.PLAYING,
    ).update(
        status=GameTurn.Status.AWAITING_ANSWER,
        playback_stopped_at=playback_stopped_at,
    )

    # Another request may have stopped the turn first.
    if updated_count == 0:
        return

    genre = turn.genre

    event_data = {
        "game_id": str(game.pk),
        "turn_id": str(turn.pk),
        "turn_status": GameTurn.Status.AWAITING_ANSWER,
        "reason": "clip_complete",
        "playback_stopped_at": (
            playback_stopped_at.isoformat()
        ),
        "team": {
            "id": str(turn.team.pk),
            "name": turn.team.name,
            "color": turn.team.color,
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

    try:
        broadcast_game_event(
            game.join_token,
            "playback.stopped",
            event_data,
        )
    except Exception:
        # The playback has already stopped successfully. A temporary
        # Redis/WebSocket failure should not mark this Celery task as
        # failed or change the completed database update.
        logger.exception(
            "Could not broadcast playback.stopped for turn %s.",
            turn_id,
        )