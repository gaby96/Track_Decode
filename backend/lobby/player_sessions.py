from uuid import UUID

from django.contrib.sessions.backends.base import SessionBase

from .models import Player

PLAYER_SESSIONS_KEY = "player_sessions"

def bind_player_to_session(session: SessionBase, *, join_token: UUID, player:Player) -> None:
    stored_sessions = session.get(PLAYER_SESSIONS_KEY, {})

    if not isinstance(stored_sessions, dict):
        stored_sessions = {}

    player_sessions = {
        str(key): str(value)
        for key, value in stored_sessions.items()
    }

    player_sessions[str(join_token)] = str(player.pk)

    session.cycle_key()
    session[PLAYER_SESSIONS_KEY] = player_sessions

def get_session_player(
     session: SessionBase,
     *,
     join_token: UUID   
) -> Player | None:
    stored_sessions = session.get(PLAYER_SESSIONS_KEY, {})

    if not isinstance(stored_sessions, dict):
        return None

    raw_player_id = stored_sessions.get(str(join_token))

    if not isinstance(raw_player_id, str):
        return None

    try:
        player_id = UUID(raw_player_id)
    except ValueError:
        return None

    return(
        Player.objects.select_related("team")
        .filter(
            pk=player_id,
            game__join_token=join_token
        )
        .first()
    )
