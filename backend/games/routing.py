from typing import Any, cast

from django.urls import path
from django.urls.resolvers import URLPattern

from .consumers import GameConsumer

websocket_urlpatterns: list[URLPattern] = [
    path(
        "ws/games/<uuid:join_token>/",
        cast(Any, GameConsumer.as_asgi()),
        name="game-websocket",
    ),
]