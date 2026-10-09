import hashlib
import secrets
import time
from datetime import timedelta
from functools import partial
from typing import cast
from urllib.parse import urlencode
from uuid import UUID

import httpx
from celery import Task
from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from gameplay.models import GameTurn, ScoreEvent
from lobby.models import LeaderVote, Player, Team
from music.models import Genre, Track
from games.realtime import broadcast_game_event
from games.serializers import (
    AwardScoreSerializer,
    GameRoundsPerTeamUpdateSerializer,
    GameSerializer,
    GameTurnSerializer,
    GenreSerializer,
    HostTrackSerializer,
    LeaderVoteSubmitSerializer,
    PlayerJoinSerializer,
    PlayerSessionSerializer,
    PublicGameSerializer,
    PublicPlayerSerializer,
    ScoreEventSerializer,
    SpotifyDeviceSelectionSerializer,
    TeamSerializer,
)
from spotify.services import (
    SpotifyNotConnectedError,
    SpotifyServiceError,
    get_valid_access_token,
)
from spotify.tasks import stop_spotify_playback

class AssignTeamsView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(
        self,
        request: Request,
        game_id: UUID,
    ):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.registration_open:
                return Response(
                    {
                        "detail": ("Close registration before assigning teams."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if game.status != Game.Status.LOBBY_CLOSED:
                return Response(
                    {
                        "detail": (
                            "Teams can only be assigned after the lobby "
                            "has been closed."
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            players = list(Player.objects.select_for_update().filter(game=game))

            if len(players) < game.number_of_teams:
                return Response(
                    {
                        "detail": ("There must be at least one player for each team."),
                        "player_count": len(players),
                        "number_of_teams": game.number_of_teams,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # Securely randomize player order.
            secrets.SystemRandom().shuffle(players)

            team_colors = [
                "#EF4444",
                "#3B82F6",
                "#22C55E",
                "#F59E0B",
                "#8B5CF6",
                "#EC4899",
                "#06B6D4",
                "#F97316",
            ]

            created_teams: list[Team] = []

            for position in range(1, game.number_of_teams + 1):
                team = Team.objects.create(
                    game=game,
                    name=f"Team {position}",
                    color=team_colors[(position - 1) % len(team_colors)],
                    position=position,
                )
                created_teams.append(team)

            # Assign players in rotation. This guarantees that team sizes
            # differ by no more than one player.
            for index, player in enumerate(players):
                assigned_team = created_teams[index % len(created_teams)]

                Player.objects.filter(pk=player.pk).update(team=assigned_team)
                player.team = assigned_team

            # Solo-player teams do not need a separate election step.
            for team in created_teams:
                members = [player for player in players if player.team_id == team.pk]

                if len(members) != 1:
                    continue

                leader = members[0]
                Team.objects.filter(pk=team.pk).update(leader=leader)
                team.leader = leader
                team.leader_id = leader.pk

            game.status = Game.Status.TEAMS_ASSIGNED
            game.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            teams_payload: list[dict[str, object]] = []

            teams = Team.objects.filter(game=game).order_by("position")

            for team in teams:
                team_players = Player.objects.filter(team=team).order_by("display_name")

                teams_payload.append(
                    {
                        "id": str(team.pk),
                        "name": team.name,
                        "color": team.color,
                        "position": team.position,
                        "players": [
                            {
                                "id": str(player.pk),
                                "display_name": player.display_name,
                            }
                            for player in team_players
                        ],
                    }
                )

            response_data = {
                "game_id": str(game.pk),
                "status": game.status,
                "teams": teams_payload,
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "teams.assigned",
                    response_data,
                )
            )

        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )


