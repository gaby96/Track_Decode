import hashlib
import secrets
from functools import partial
from typing import cast
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from games.realtime import broadcast_game_event
from games.serializers import (
    PlayerJoinSerializer,
    PlayerSessionSerializer,
    PublicPlayerSerializer,
)
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from lobby.models import Player


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

        session_token = secrets.token_urlsafe(32)
        session_token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()

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
                session_token_hash=session_token_hash,
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

        return Response(
            {
                "player": PublicPlayerSerializer(player).data,
                "session_token": session_token,
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

    def post(
        self,
        request: Request,
        join_token: UUID,
    ) -> Response:
        game = get_object_or_404(
            Game,
            join_token=join_token,
        )

        serializer = PlayerSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = cast(dict[str, str], serializer.validated_data)
        session_token = validated_data["session_token"]
        session_token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()

        player = (
            Player.objects.select_related("team")
            .filter(
                game=game,
                session_token_hash=session_token_hash,
            )
            .first()
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


