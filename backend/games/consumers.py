from typing import Any, cast
from uuid import UUID

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Game


class GameConsumer(AsyncJsonWebsocketConsumer):
    game_group_name: str

    async def connect(self) -> None:
        scope = cast(dict[str, Any], self.scope)
        url_route = scope.get("url_route", {})
        route_kwargs = url_route.get("kwargs", {})
        join_token = route_kwargs.get("join_token")

        if not isinstance(join_token, UUID):
            await self.close(code=4000)
            return

        game_exists = await Game.objects.filter(
            join_token=join_token,
        ).aexists()

        if not game_exists:
            await self.close(code=4004)
            return

        self.game_group_name = f"game_{join_token}"

        channel_layer = self.channel_layer
        if channel_layer is None:
            await self.close(code=1011)
            return

        await channel_layer.group_add(
            self.game_group_name,
            self.channel_name,
        )

        await self.accept()

        await self.send_json(
            {
                "type": "connection.ready",
                "join_token": str(join_token),
            }
        )

    async def disconnect(self, code: int) -> None:
        game_group_name = getattr(self, "game_group_name", None)
        channel_layer = self.channel_layer

        if game_group_name is not None and channel_layer is not None:
            await channel_layer.group_discard(
                game_group_name,
                self.channel_name,
            )
    async def game_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", {})
        await self.send_json(payload)