
import random
from functools import partial
from typing import cast

from django.contrib.sessions.backends.base import SessionBase
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from gameplay.models import GameTurn
from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from games.realtime import broadcast_game_event
from games.serializers import (
    GameTurnSerializer,
    GenreSerializer,
)
from lobby.models import Team
from lobby.player_sessions import get_session_player
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from music.models import Genre


@method_decorator(csrf_protect, name="dispatch")
class SelectRandomGenreView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request, join_token, turn_id):
        session = cast(SessionBase, request.session)

        player = get_session_player(
            session,
            join_token=join_token,
        )

        if player is None:
            return Response(
                {
                    "detail": STRING_ERROR_RESPONSES["invalid_player_session"]
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
        with transaction.atomic():
            locked_game = get_object_or_404(
                Game.objects.select_for_update(),
                join_token=join_token,
            )

            if locked_game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {"detail": ("The game is not currently in progress.")},
                    status=status.HTTP_409_CONFLICT,
                )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related("team"),
                pk=turn_id,
                game=locked_game,
            )

            if turn.status != GameTurn.Status.ACTIVE:
                return Response(
                    {
                        "detail": "This is not the active turn.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )


            is_active_leader = Team.objects.filter(
                pk=turn.team.pk,
                game=locked_game,
                leader=player,
            ).exists()

            if not is_active_leader:
                return Response(
                    {
                        "detail": (
                            "Only the active team's elected leader "
                            "can select the genre."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            genres = list(
                Genre.objects.filter(
                    is_enabled=True,
                ).order_by("name")
            )

            if not genres:
                return Response(
                    {
                        "detail": "No music genres have been enabled.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            used_genre_ids = set(
                GameTurn.objects.filter(
                    game=locked_game,
                    genre__isnull=False,
                ).values_list(
                    "genre",
                    flat=True,
                )
            )

            unused_genres = [
                genre for genre in genres if genre.pk not in used_genre_ids
            ]

            selection_pool = unused_genres or genres

            selected_genre = random.SystemRandom().choice(selection_pool)

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                genre=selected_genre,
                status=GameTurn.Status.GENRE_SELECTED,
            )

            updated_turn = GameTurn.objects.select_related(
                "team",
                "genre",
            ).get(pk=turn.pk)

            event_data = {
                "game_id": str(locked_game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
                },
                "genre": {
                    "id": str(selected_genre.pk),
                    "name": selected_genre.name,
                    "color": selected_genre.color,
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    locked_game.join_token,
                    "genre.selected",
                    event_data,
                )
            )

        return Response(
            {
                "turn": GameTurnSerializer(updated_turn).data,
                "genre": GenreSerializer(selected_genre).data,
            },
            status=status.HTTP_200_OK,
        )


