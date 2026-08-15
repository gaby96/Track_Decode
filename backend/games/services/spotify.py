import time
from typing import Any, cast

import httpx
from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.contrib.sessions.models import Session
from django.utils import timezone


class SpotifyNotConnectedError(Exception):
    pass


class SpotifyServiceError(Exception):
    pass


def _hydrate_spotify_tokens_from_other_session(
    session: SessionBase,
    user_id: object | None,
) -> bool:
    if user_id is None:
        return False

    normalized_user_id = str(user_id)
    current_session_key = getattr(session, "session_key", None)

    for candidate in Session.objects.filter(
        expire_date__gt=timezone.now(),
    ).order_by("-expire_date"):
        if candidate.session_key == current_session_key:
            continue

        decoded = candidate.get_decoded()

        if str(decoded.get("_auth_user_id")) != normalized_user_id:
            continue

        tokens = decoded.get("spotify_tokens")

        if not isinstance(tokens, dict) or not tokens:
            continue

        session["spotify_tokens"] = tokens
        session.modified = True
        return True

    return False


def get_valid_access_token(
    session: SessionBase,
    *,
    user_id: object | None = None,
) -> str:
    tokens = cast(
        dict[str, Any] | None,
        session.get("spotify_tokens"),
    )

    if not tokens:
        if not _hydrate_spotify_tokens_from_other_session(
            session,
            user_id,
        ):
            raise SpotifyNotConnectedError

        tokens = cast(
            dict[str, Any] | None,
            session.get("spotify_tokens"),
        )

        if not tokens:
            raise SpotifyNotConnectedError

    access_token = tokens.get("access_token")
    expires_at = int(cast(int, tokens.get("expires_at", 0)))

    if access_token and expires_at > int(time.time()) + 60:
        return cast(str, access_token)

    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        session.pop("spotify_tokens", None)
        raise SpotifyNotConnectedError

    client_id = cast(
        str,
        getattr(settings, "SPOTIFY_CLIENT_ID"),
    )
    client_secret = cast(
        str,
        getattr(settings, "SPOTIFY_CLIENT_SECRET"),
    )

    try:
        response = httpx.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(client_id, client_secret),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SpotifyServiceError from error

    refreshed_data = response.json()
    refreshed_access_token = refreshed_data.get("access_token")

    if not refreshed_access_token:
        raise SpotifyServiceError

    session["spotify_tokens"] = {
        "access_token": refreshed_access_token,
        "refresh_token": refreshed_data.get(
            "refresh_token",
            refresh_token,
        ),
        "expires_at": (
            int(time.time())
            + int(refreshed_data.get("expires_in", 3600))
        ),
    }
    session.modified = True

    return cast(str, refreshed_access_token)
