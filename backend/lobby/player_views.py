from functools import partial
from typing import cast
from uuid import UUID

from django.contrib.sessions.backends.base import SessionBase
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from games.realtime import broadcast_game_event
from games.serializers import (
    PlayerJoinSerializer,
    PublicPlayerSerializer,
)
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from lobby.models import Player
from lobby.player_sessions import bind_player_to_session, get_session_player


@method_decorator(csrf_protect, name="dispatch")
class PlayerJoinView(APIView):
    permission_classes = (AllowAny,)

    def post(
        self,
        request: Request,
        join_token: UUID,
    ) -> Response:
        serializer = PlayerJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = cast(
            dict[str, object],
            serializer.validated_data,
        )
        display_name = cast(str, validated_data["display_name"])

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                join_token=join_token,
            )

            if not game.registration_open or game.status != Game.Status.LOBBY_OPEN:
                return Response(
                    {
                        "detail": "Registration for this game is closed.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            player = Player.objects.create(
                game=game,
                display_name=display_name,
            )

            player_count = Player.objects.filter(game=game).count()

            player_event_data = {
                "id": str(player.pk),
                "display_name": player.display_name,
                "team_id": None,
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "player.joined",
                    {
                        "player": player_event_data,
                        "player_count": player_count,
                    },
                )
            )

        session = cast(SessionBase, request.session)

        bind_player_to_session(
            session,
            join_token=game.join_token,
            player=player,
        )

        return Response(
            {
                "player": PublicPlayerSerializer(player).data,
            },
            status=status.HTTP_201_CREATED,
        )


class HostPlayerListView(generics.ListAPIView):
    queryset = Player.objects.all()
    serializer_class = PublicPlayerSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                game_id=self.kwargs["game_id"],
                game__host=self.request.user,
            )
            .select_related("team")
            .order_by("joined_at")
        )


class PlayerSessionDetailView(APIView):
    permission_classes = (AllowAny,)

    def get(
        self,
        request: Request,
        join_token: UUID,
    ) -> Response:
        session = cast(SessionBase, request.session)

        player = get_session_player(
            session,
            join_token=join_token
        )

        if player is None:
            return Response(
                {"detail": STRING_ERROR_RESPONSES["invalid_player_session"]},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "player": PublicPlayerSerializer(player).data,
            },
            status=status.HTTP_200_OK,
        )


