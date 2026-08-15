from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_game_event(
    join_token: UUID | str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    channel_layer = get_channel_layer()

    if channel_layer is None:
        raise RuntimeError("The Django Channels layer is not configured.")

    async_to_sync(channel_layer.group_send)(
        f"game_{join_token}",
        {
            # Channels converts "game.event" into the game_event()
            # consumer method.
            "type": "game.event",
            "payload": {
                "type": event_type,
                "data": data,
            },
        },
    )