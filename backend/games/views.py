import hashlib
import random
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
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Game,
    GameTurn,
    Genre,
    LeaderVote,
    Player,
    ScoreEvent,
    Team,
    Track,
)
from .realtime import broadcast_game_event
from .serializers import (
    AwardScoreSerializer,
    GameSerializer,
    GameRoundsPerTeamUpdateSerializer,
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
from .services.spotify import (
    SpotifyNotConnectedError,
    SpotifyServiceError,
    get_valid_access_token,
)
from .tasks import stop_spotify_playback


PLAYBACK_CLIP_DURATION_SECONDS = 15


def _find_replacement_spotify_device(
    *,
    access_token: str,
    saved_device_id: str,
    saved_device_name: str,
) -> dict[str, object] | None:
    normalized_name = saved_device_name.strip()

    if not normalized_name:
        return None

    devices_response = httpx.get(
        "https://api.spotify.com/v1/me/player/devices",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=15.0,
    )
    devices_response.raise_for_status()

    response_data = cast(
        dict[str, object],
        devices_response.json(),
    )
    raw_devices = response_data.get("devices", [])
    devices = raw_devices if isinstance(raw_devices, list) else []

    matching_devices = [
        device
        for device in devices
        if (
            isinstance(device, dict)
            and isinstance(device.get("id"), str)
            and device.get("id") != saved_device_id
            and device.get("name") == normalized_name
            and device.get("is_restricted") is not True
        )
    ]

    if not matching_devices:
        return None

    active_match = next(
        (
            device
            for device in matching_devices
            if device.get("is_active") is True
        ),
        None,
    )

    return active_match or matching_devices[0]


class GameListCreateView(generics.ListCreateAPIView):
    queryset = Game.objects.all()
    serializer_class = GameSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                host=self.request.user,
            )
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(host=self.request.user)


class PublicGameDetailView(generics.RetrieveAPIView):
    queryset = Game.objects.all()
    serializer_class = PublicGameSerializer
    permission_classes = (AllowAny,)
    lookup_field = "join_token"
    lookup_url_kwarg = "join_token"


class PublicGameByCodeDetailView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request: Request, join_code: str) -> Response:
        normalized_join_code = join_code.strip().upper()
        game = get_object_or_404(
            Game,
            join_code=normalized_join_code,
        )

        return Response(
            PublicGameSerializer(game).data,
            status=status.HTTP_200_OK,
        )


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
        session_token_hash = hashlib.sha256(
            session_token.encode("utf-8")
        ).hexdigest()

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
                {"detail": "Invalid player session."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "player": PublicPlayerSerializer(player).data,
            },
            status=status.HTTP_200_OK,
        )


class CloseRegistrationView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.status != Game.Status.LOBBY_OPEN:
                return Response(
                    {"detail": "The game is not accepting registration changes."},
                    status=status.HTTP_409_CONFLICT,
                )

            game.registration_open = False
            game.status = Game.Status.LOBBY_CLOSED
            game.save(
                update_fields=(
                    "registration_open",
                    "status",
                    "updated_at",
                )
            )

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "registration.closed",
                    {
                        "game_id": str(game.pk),
                        "registration_open": False,
                        "status": game.status,
                    },
                )
            )

        return Response(
            GameSerializer(game).data,
            status=status.HTTP_200_OK,
        )


class UpdateGameRoundsView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, game_id):
        serializer = GameRoundsPerTeamUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = cast(
            dict[str, int],
            serializer.validated_data,
        )
        rounds_per_team = validated_data["rounds_per_team"]

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if (
                game.status in (
                    Game.Status.IN_PROGRESS,
                    Game.Status.PAUSED,
                )
                and rounds_per_team < game.current_round
            ):
                return Response(
                    {
                        "detail": (
                            "Rounds per team cannot be set below the "
                            "current round while the game is in progress."
                        ),
                        "current_round": game.current_round,
                        "rounds_per_team": game.rounds_per_team,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            game.rounds_per_team = rounds_per_team
            game.save(
                update_fields=[
                    "rounds_per_team",
                    "updated_at",
                ]
            )

            event_data = {
                "game_id": str(game.pk),
                "rounds_per_team": game.rounds_per_team,
                "status": game.status,
                "current_round": game.current_round,
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "game.updated",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            GameSerializer(game).data,
            status=status.HTTP_200_OK,
        )


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
            random.SystemRandom().shuffle(players)

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
                members = [
                    player for player in players if player.team_id == team.pk
                ]

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


class OpenVotingView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.status != Game.Status.TEAMS_ASSIGNED:
                return Response(
                    {"detail": ("Teams must be assigned before voting can open.")},
                    status=status.HTTP_409_CONFLICT,
                )

            teams = list(Team.objects.filter(game=game).order_by("position"))

            if len(teams) != game.number_of_teams:
                return Response(
                    {"detail": "The game does not have the expected teams."},
                    status=status.HTTP_409_CONFLICT,
                )

            if Player.objects.filter(
                game=game,
                team__isnull=True,
            ).exists():
                return Response(
                    {"detail": "Some players have not been assigned to teams."},
                    status=status.HTTP_409_CONFLICT,
                )

            auto_elected_leaders: list[dict[str, object]] = []
            teams_requiring_votes = 0

            for team in teams:
                members = list(
                    Player.objects.filter(
                        game=game,
                        team=team,
                    ).order_by("joined_at")
                )

                if len(members) == 1:
                    leader = members[0]

                    if team.leader_id != leader.pk:
                        Team.objects.filter(pk=team.pk).update(leader=leader)
                        team.leader = leader

                    auto_elected_leaders.append(
                        {
                            "team": {
                                "id": str(team.pk),
                                "name": team.name,
                            },
                            "leader": {
                                "id": str(leader.pk),
                                "display_name": leader.display_name,
                            },
                            "votes": 1,
                            "tie_break_used": False,
                            "auto_elected": True,
                        }
                    )
                    continue

                teams_requiring_votes += 1

            game.status = (
                Game.Status.VOTING_CLOSED
                if teams_requiring_votes == 0
                else Game.Status.VOTING_OPEN
            )
            game.save(update_fields=("status", "updated_at"))

            if game.status == Game.Status.VOTING_CLOSED:
                transaction.on_commit(
                    partial(
                        broadcast_game_event,
                        game.join_token,
                        "voting.closed",
                        {
                            "game_id": str(game.pk),
                            "status": game.status,
                            "teams": [
                                {
                                    "team_id": leader_result["team"]["id"],
                                    "team_name": leader_result["team"]["name"],
                                    "leader": leader_result["leader"],
                                }
                                for leader_result in auto_elected_leaders
                            ],
                        },
                    )
                )
            else:
                transaction.on_commit(
                    partial(
                        broadcast_game_event,
                        game.join_token,
                        "voting.opened",
                        {
                            "game_id": str(game.pk),
                            "status": game.status,
                            "auto_elected_leaders": auto_elected_leaders,
                        },
                    )
                )

        return Response(
            {
                "game": GameSerializer(game).data,
                "teams": TeamSerializer(teams, many=True).data,
                "leaders": auto_elected_leaders,
            },
            status=status.HTTP_200_OK,
        )


class SubmitLeaderVoteView(APIView):
    permission_classes = (AllowAny,)

    def post(
        self,
        request: Request,
        join_token: UUID,
    ) -> Response:
        session_token = request.headers.get(
            "X-Player-Token",
            "",
        ).strip()

        if not session_token:
            return Response(
                {
                    "detail": "The X-Player-Token header is required.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        request_data = cast(dict[str, object], request.data)
        candidate_id_value = request_data.get("candidate_id")

        if not isinstance(candidate_id_value, str):
            return Response(
                {
                    "detail": "candidate_id is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            candidate_id = UUID(candidate_id_value)
        except ValueError:
            return Response(
                {
                    "detail": "candidate_id must be a valid UUID.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_token_hash = hashlib.sha256(
            session_token.encode("utf-8")
        ).hexdigest()

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                join_token=join_token,
            )

            if game.status != Game.Status.VOTING_OPEN:
                return Response(
                    {
                        "detail": "Leader voting is not currently open.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            voter = (
                Player.objects.select_for_update()
                .select_related("team")
                .filter(
                    game=game,
                    session_token_hash=session_token_hash,
                )
                .first()
            )

            if voter is None:
                return Response(
                    {
                        "detail": "The player token is invalid.",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            team = voter.team

            if team is None:
                return Response(
                    {
                        "detail": (
                            "The player has not been assigned to a team."
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            team_player_count = Player.objects.filter(
                team=team,
            ).count()

            if team_player_count <= 1:
                return Response(
                    {
                        "detail": (
                            "Leader voting is not required when your team "
                            "has only one player."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if LeaderVote.objects.filter(
                team=team,
                voter=voter,
            ).exists():
                return Response(
                    {
                        "detail": "You have already submitted your leader vote.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            candidate = (
                Player.objects.select_for_update()
                .filter(
                    pk=candidate_id,
                    game=game,
                    team=team,
                )
                .first()
            )

            if candidate is None:
                return Response(
                    {
                        "detail": (
                            "The selected candidate is not a member "
                            "of your team."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            LeaderVote.objects.create(
                team=team,
                voter=voter,
                candidate=candidate,
            )

            votes_submitted = LeaderVote.objects.filter(
                team=team,
            ).count()

            voting_progress = {
                "team_id": str(team.pk),
                "votes_submitted": votes_submitted,
                "team_player_count": team_player_count,
                "voting_complete": (
                    votes_submitted >= team_player_count
                ),
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "voting.progress",
                    voting_progress,
                )
            )

        return Response(
            {
                "detail": (
                    "Leader vote submitted."
                ),
                "team_id": str(team.pk),
                "votes_submitted": votes_submitted,
                "team_player_count": team_player_count,
                "voting_complete": (
                    votes_submitted >= team_player_count
                ),
            },
            status=(
                status.HTTP_201_CREATED
            ),
        )


class TeamVotingCandidatesView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request, join_token):
        game = get_object_or_404(Game, join_token=join_token)

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
                {"detail": "Invalid player session."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        team = player.team

        if team is None:
            return Response(
                {"detail": "You have not been assigned to a team."},
                status=status.HTTP_409_CONFLICT,
            )

        candidates = Player.objects.filter(
            game=game,
            team=team,
        ).order_by("joined_at")
        team_player_count = candidates.count()
        requires_vote = team_player_count > 1

        has_voted = LeaderVote.objects.filter(
            team=team,
            voter=player,
        ).exists()

        return Response(
            {
                "game_status": game.status,
                "team": {
                    "id": team.pk,
                    "name": team.name,
                    "color": team.color,
                },
                "player": PublicPlayerSerializer(player).data,
                "candidates": PublicPlayerSerializer(
                    candidates,
                    many=True,
                ).data,
                "team_player_count": team_player_count,
                "has_voted": has_voted,
                "requires_vote": requires_vote,
            },
            status=status.HTTP_200_OK,
        )


class CloseVotingView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.status != Game.Status.VOTING_OPEN:
                return Response(
                    {"detail": "Leader voting is not open."},
                    status=status.HTTP_409_CONFLICT,
                )

            teams = list(
                Team.objects.select_for_update().filter(game=game).order_by("position")
            )

            leader_results = []

            for team in teams:
                members = list(
                    Player.objects.filter(
                        game=game,
                        team=team,
                    ).order_by("joined_at")
                )

                votes = list(
                    LeaderVote.objects.filter(
                        team=team,
                    ).select_related("candidate")
                )

                if len(members) == 1:
                    leader = members[0]
                    if team.leader_id != leader.pk:
                        Team.objects.filter(pk=team.pk).update(leader=leader)
                        team.leader = leader
                        team.leader_id = leader.pk

                    leader_results.append(
                        {
                            "team": {
                                "id": team.pk,
                                "name": team.name,
                            },
                            "leader": {
                                "id": leader.pk,
                                "display_name": leader.display_name,
                            },
                            "votes": 1,
                            "tie_break_used": False,
                            "auto_elected": True,
                        }
                    )
                    continue

                if len(votes) < len(members):
                    return Response(
                        {
                            "detail": (
                                f"Voting is incomplete for {team.name}. "
                                f"{len(votes)} of {len(members)} players "
                                "have voted."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                vote_totals: dict[object, int] = {}

                for vote in votes:
                    candidate_key = vote.candidate.pk
                    vote_totals[candidate_key] = vote_totals.get(candidate_key, 0) + 1

                highest_total = max(vote_totals.values())

                winning_ids = [
                    candidate_id
                    for candidate_id, total in vote_totals.items()
                    if total == highest_total
                ]

                winning_id = secrets.SystemRandom().choice(winning_ids)

                leader = next(member for member in members if member.pk == winning_id)

                Team.objects.filter(pk=team.pk).update(leader=leader)

                leader_results.append(
                    {
                        "team": {
                            "id": team.pk,
                            "name": team.name,
                        },
                        "leader": {
                            "id": leader.pk,
                            "display_name": leader.display_name,
                        },
                        "votes": highest_total,
                        "tie_break_used": len(winning_ids) > 1,
                    }
                )

            game.status = Game.Status.VOTING_CLOSED
            game.save(update_fields=("status", "updated_at"))

            leaders_payload: list[dict[str, object]] = []

        teams = (
            Team.objects.filter(game=game)
            .select_related("leader")
            .order_by("position")
        )

        for team in teams:
            leader = team.leader

            leaders_payload.append(
                {
                    "team_id": str(team.pk),
                    "team_name": team.name,
                    "leader": (
                        {
                            "id": str(leader.pk),
                            "display_name": leader.display_name,
                        }
                        if leader is not None
                        else None
                    ),
                }
            )

        event_data = {
            "game_id": str(game.pk),
            "status": game.status,
            "teams": leaders_payload,
        }

        transaction.on_commit(
            partial(
                broadcast_game_event,
                game.join_token,
                "voting.closed",
                event_data,
            )
        )

        return Response(
            {
                "game": GameSerializer(game).data,
                "leaders": leader_results,
            },
            status=status.HTTP_200_OK,
        )


class StartGameView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.status != Game.Status.VOTING_CLOSED:
                return Response(
                    {
                        "detail": (
                            "Leader voting must be completed before the game can start."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if GameTurn.objects.filter(game=game).exists():
                return Response(
                    {"detail": "This game has already been started."},
                    status=status.HTTP_409_CONFLICT,
                )

            teams = list(
                Team.objects.select_for_update().filter(game=game).order_by(
                    "position"
                )
            )

            if not teams:
                return Response(
                    {"detail": "This game does not have any teams."},
                    status=status.HTTP_409_CONFLICT,
                )

            for team in teams:
                if team.leader_id is not None:
                    continue

                members = list(
                    Player.objects.filter(
                        game=game,
                        team=team,
                    ).order_by("joined_at")
                )

                if len(members) != 1:
                    continue

                leader = members[0]
                Team.objects.filter(pk=team.pk).update(leader=leader)
                team.leader = leader
                team.leader_id = leader.pk

            if any(team.leader_id is None for team in teams):
                return Response(
                    {"detail": "Every team must have an elected leader."},
                    status=status.HTTP_409_CONFLICT,
                )

            secrets.SystemRandom().shuffle(teams)
            started_at = timezone.now()

            turns = [
                GameTurn(
                    game=game,
                    team=team,
                    round_number=1,
                    turn_position=index,
                    status=(
                        GameTurn.Status.ACTIVE
                        if index == 1
                        else GameTurn.Status.WAITING
                    ),
                    started_at=started_at if index == 1 else None,
                )
                for index, team in enumerate(teams, start=1)
            ]

            GameTurn.objects.bulk_create(turns)

            game.status = Game.Status.IN_PROGRESS
            game.current_round = 1
            game.save(
                update_fields=[
                    "status",
                    "current_round",
                    "updated_at",
                ]
            )

            active_turn = (
                GameTurn.objects.filter(
                    game=game,
                    status=GameTurn.Status.ACTIVE,
                )
                .select_related("team")
                .order_by("round_number", "turn_position")
                .first()
            )

            if active_turn is None:
                return Response(
                    {
                        "detail": "The game has no active turn.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            event_data = {
                "game_id": str(game.pk),
                "status": game.status,
                "current_round": game.current_round,
                "active_turn": {
                    "id": str(active_turn.pk),
                    "round_number": active_turn.round_number,
                    "turn_position": active_turn.turn_position,
                    "status": active_turn.status,
                    "team": {
                        "id": str(active_turn.team.pk),
                        "name": active_turn.team.name,
                        "color": active_turn.team.color,
                    },
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "game.started",
                    event_data,
                )
            )

        return Response(
            {
                "game": GameSerializer(game).data,
                "active_turn": GameTurnSerializer(turns[0]).data,
                "turns": GameTurnSerializer(turns, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class SelectRandomGenreView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request, join_token, turn_id):
        game = get_object_or_404(
            Game,
            join_token=join_token,
        )

        serializer = PlayerSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = cast(
            dict[str, str],
            serializer.validated_data,
        )
        session_token = validated_data["session_token"]

        session_token_hash = hashlib.sha256(
            session_token.encode("utf-8")
        ).hexdigest()

        with transaction.atomic():
            locked_game = Game.objects.select_for_update().get(
                pk=game.pk
            )

            if locked_game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": (
                            "The game is not currently in progress."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "team"
                ),
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

            player = Player.objects.filter(
                game=locked_game,
                session_token_hash=session_token_hash,
            ).first()

            if player is None:
                return Response(
                    {
                        "detail": "Invalid player session.",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
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
                genre
                for genre in genres
                if genre.pk not in used_genre_ids
            ]

            selection_pool = unused_genres or genres

            selected_genre = secrets.SystemRandom().choice(
                selection_pool
            )

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                genre=selected_genre,
                status=GameTurn.Status.GENRE_SELECTED,
            )

            updated_turn = (
                GameTurn.objects.select_related(
                    "team",
                    "genre",
                ).get(pk=turn.pk)
            )

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


class SpotifyLoginView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        state = secrets.token_urlsafe(32)
        request.session["spotify_oauth_state"] = state

        scopes = (
            "streaming",
            "user-read-email",
            "user-read-private",
            "user-read-playback-state",
            "user-modify-playback-state",
        )

        parameters = {
            "client_id": settings.SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
            "state": state,
            "scope": " ".join(scopes),
        }

        authorization_url = "https://accounts.spotify.com/authorize?" + urlencode(
            parameters
        )

        return HttpResponseRedirect(authorization_url)


class SpotifyCallbackView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        spotify_error = request.query_params.get("error")

        if spotify_error:
            return Response(
                {
                    "detail": ("Spotify authorization was denied or failed."),
                    "spotify_error": spotify_error,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = request.query_params.get("code")
        returned_state = request.query_params.get("state")
        expected_state = request.session.pop(
            "spotify_oauth_state",
            None,
        )

        if (
            not code
            or not returned_state
            or not expected_state
            or not secrets.compare_digest(
                returned_state,
                expected_state,
            )
        ):
            return Response(
                {"detail": "Invalid Spotify authorization state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token_response = httpx.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
                },
                auth=(
                    settings.SPOTIFY_CLIENT_ID,
                    settings.SPOTIFY_CLIENT_SECRET,
                ),
                headers={"Content-Type": ("application/x-www-form-urlencoded")},
                timeout=15.0,
            )
            token_response.raise_for_status()
        except httpx.HTTPError:
            return Response(
                {"detail": "Spotify token exchange failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        token_data = token_response.json()

        request.session["spotify_tokens"] = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": (
                int(time.time())
                + int(cast(int, token_data.get("expires_in", 3600)))
            ),
        }

        request.session.modified = True

        return Response(
            {
                "connected": True,
                "detail": "Spotify connected successfully.",
            },
            status=status.HTTP_200_OK,
        )


class SpotifyStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        session = cast(
            SessionBase,
            getattr(request, "session"),
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)

            profile_response = httpx.get(
                "https://api.spotify.com/v1/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=15.0,
            )
            profile_response.raise_for_status()
        except SpotifyNotConnectedError:
            return Response(
                {
                    "connected": False,
                    "detail": "Spotify has not been connected.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (SpotifyServiceError, httpx.HTTPError):
            return Response(
                {
                    "connected": False,
                    "detail": "Spotify could not be reached.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        profile = profile_response.json()
        is_premium = profile.get("product") == "premium"

        return Response(
            {
                "connected": True,
                "premium": is_premium,
                "display_name": profile.get("display_name"),
                "country": profile.get("country"),
                "spotify_user_id": profile.get("id"),
                "playback_available": is_premium,
            },
            status=status.HTTP_200_OK,
        )


class PrepareRandomTrackView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        session = cast(
            SessionBase,
            getattr(request, "session"),
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": (
                        "Connect Spotify before selecting a track."
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except SpotifyServiceError:
            return Response(
                {
                    "detail": "Spotify authentication failed.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "genre",
                    "team",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": "The game is not in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status != GameTurn.Status.GENRE_SELECTED:
                return Response(
                    {
                        "detail": (
                            "A genre must be selected before preparing "
                            "a track."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            genre = turn.genre

            if genre is None:
                return Response(
                    {
                        "detail": "This turn does not have a genre.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            playlist_id = genre.spotify_playlist_id.strip()

            if not playlist_id:
                return Response(
                    {
                        "detail": (
                            f"{genre.name} does not have a Spotify playlist."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            used_track_ids = set(
                GameTurn.objects.filter(
                    game=game,
                    track__isnull=False,
                ).values_list(
                    "track__spotify_track_id",
                    flat=True,
                )
            )

            headers = {
                "Authorization": f"Bearer {access_token}",
            }

            playlist_url = (
                f"https://api.spotify.com/v1/playlists/"
                f"{playlist_id}/items"
            )

            try:
                total_response = httpx.get(
                    playlist_url,
                    headers=headers,
                    params={
                        "fields": "total",
                    },
                    timeout=15.0,
                )
                total_response.raise_for_status()

                total_response_data = cast(
                    dict[str, object],
                    total_response.json(),
                )

                total = int(cast(int, total_response_data.get("total", 0)))
            except (
                httpx.HTTPError,
                TypeError,
                ValueError,
            ):
                return Response(
                    {
                        "detail": (
                            "Spotify could not read this genre playlist."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if total == 0:
                return Response(
                    {
                        "detail": "The Spotify playlist is empty.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            page_size = min(50, total)
            maximum_offset = max(0, total - page_size)

            offsets = {0}

            while len(offsets) < min(
                4,
                maximum_offset + 1,
            ):
                offsets.add(
                    secrets.SystemRandom().randint(
                        0,
                        maximum_offset,
                    )
                )

            candidates: list[dict[str, object]] = []

            try:
                for offset in offsets:
                    playlist_response = httpx.get(
                        playlist_url,
                        headers=headers,
                        params={
                            "limit": page_size,
                            "offset": offset,
                            "market": "from_token",
                        },
                        timeout=15.0,
                    )
                    playlist_response.raise_for_status()

                    response_data = cast(
                        dict[str, object],
                        playlist_response.json(),
                    )

                    items = cast(
                        list[dict[str, object]],
                        response_data.get(
                            "items",
                            [],
                        ),
                    )

                    for playlist_item in items:
                        if playlist_item.get("is_local") is True:
                            continue

                        spotify_item = playlist_item.get("item")

                        # Compatibility with Spotify's older
                        # playlist response format.
                        if spotify_item is None:
                            spotify_item = playlist_item.get("track")

                        if not isinstance(spotify_item, dict):
                            continue

                        if spotify_item.get("type") != "track":
                            continue

                        spotify_track_id = spotify_item.get("id")
                        spotify_uri = spotify_item.get("uri")
                        duration_ms = spotify_item.get("duration_ms")

                        if not isinstance(spotify_track_id, str):
                            continue

                        if not isinstance(spotify_uri, str):
                            continue

                        if not isinstance(duration_ms, int):
                            continue

                        if duration_ms < 10_000:
                            continue

                        if spotify_track_id in used_track_ids:
                            continue

                        is_explicit = bool(
                            spotify_item.get(
                                "explicit",
                                False,
                            )
                        )

                        if genre.exclude_explicit and is_explicit:
                            continue

                        if spotify_item.get("is_playable") is False:
                            continue

                        candidates.append(spotify_item)

            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    return Response(
                        {
                            "detail": (
                                "Spotify rate limit reached. "
                                "Try again later."
                            )
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                return Response(
                    {
                        "detail": (
                            "Spotify could not load playlist tracks."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            except httpx.HTTPError:
                return Response(
                    {
                        "detail": "Spotify could not be reached.",
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if not candidates:
                return Response(
                    {
                        "detail": (
                            "No eligible unused tracks were found "
                            "in this playlist."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            selected = secrets.SystemRandom().choice(candidates)

            album_data = selected.get("album")
            album = album_data if isinstance(album_data, dict) else {}

            artists_data = selected.get("artists")
            artists = (
                artists_data
                if isinstance(artists_data, list)
                else []
            )

            artist_names = [
                artist["name"]
                for artist in artists
                if (
                    isinstance(artist, dict)
                    and isinstance(artist.get("name"), str)
                )
            ]

            images_data = album.get("images")
            images = (
                images_data
                if isinstance(images_data, list)
                else []
            )

            artwork_url = ""

            if images and isinstance(images[0], dict):
                image_url = images[0].get("url")

                if isinstance(image_url, str):
                    artwork_url = image_url

            spotify_track_id = cast(
                str,
                selected["id"],
            )
            spotify_uri = cast(
                str,
                selected["uri"],
            )
            title = cast(
                str,
                selected.get(
                    "name",
                    "Unknown title",
                ),
            )
            duration_ms = cast(
                int,
                selected["duration_ms"],
            )

            track, _ = Track.objects.update_or_create(
                spotify_track_id=spotify_track_id,
                defaults={
                    "spotify_uri": spotify_uri,
                    "title": title,
                    "artist": (
                        ", ".join(artist_names)
                        or "Unknown artist"
                    ),
                    "album": str(
                        album.get(
                            "name",
                            "",
                        )
                    ),
                    "artwork_url": artwork_url,
                    "duration_ms": duration_ms,
                    "is_explicit": bool(
                        selected.get(
                            "explicit",
                            False,
                        )
                    ),
                },
            )

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                track=track,
                playback_start_ms=0,
                status=GameTurn.Status.TRACK_READY,
            )

            updated_turn = (
                GameTurn.objects.select_related(
                    "team",
                    "genre",
                    "track",
                ).get(pk=turn.pk)
            )

            # This payload deliberately excludes all track information.
            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "track_ready": True,
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
                },
                "genre": {
                    "id": str(genre.pk),
                    "name": genre.name,
                    "color": genre.color,
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "track.ready",
                    event_data,
                )
            )

        return Response(
            {
                "turn": GameTurnSerializer(updated_turn).data,
                # This response is only returned to the authenticated host.
                "track": HostTrackSerializer(track).data,
            },
            status=status.HTTP_200_OK,
        )


class SpotifyDeviceListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        session = cast(
            SessionBase,
            getattr(request, "session"),
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)

            spotify_response = httpx.get(
                "https://api.spotify.com/v1/me/player/devices",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=15.0,
            )
            spotify_response.raise_for_status()
        except SpotifyNotConnectedError:
            return Response(
                {"detail": "Spotify has not been connected."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (SpotifyServiceError, httpx.HTTPError):
            return Response(
                {"detail": "Spotify devices could not be loaded."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_data = cast(
            dict[str, object],
            spotify_response.json(),
        )
        raw_devices = response_data.get("devices", [])
        devices = raw_devices if isinstance(raw_devices, list) else []

        available_devices = [
            {
                "id": device.get("id"),
                "name": device.get("name"),
                "type": device.get("type"),
                "is_active": device.get("is_active", False),
                "is_restricted": device.get(
                    "is_restricted",
                    False,
                ),
                "volume_percent": device.get("volume_percent"),
                "supports_volume": device.get(
                    "supports_volume",
                    False,
                ),
            }
            for device in devices
            if isinstance(device, dict) and isinstance(device.get("id"), str)
        ]

        return Response(
            {"devices": available_devices},
            status=status.HTTP_200_OK,
        )


class SelectSpotifyDeviceView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        serializer = SpotifyDeviceSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = cast(
            dict[str, str],
            serializer.validated_data,
        )
        requested_device_id = validated_data["device_id"]

        session = cast(
            SessionBase,
            getattr(request, "session"),
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)

            devices_response = httpx.get(
                "https://api.spotify.com/v1/me/player/devices",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=15.0,
            )
            devices_response.raise_for_status()
        except SpotifyNotConnectedError:
            return Response(
                {"detail": "Spotify has not been connected."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (SpotifyServiceError, httpx.HTTPError):
            return Response(
                {"detail": "Spotify devices could not be loaded."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_data = cast(
            dict[str, object],
            devices_response.json(),
        )
        raw_devices = response_data.get("devices", [])
        devices = raw_devices if isinstance(raw_devices, list) else []

        selected_device: dict[str, object] | None = None

        for device in devices:
            if isinstance(device, dict) and device.get("id") == requested_device_id:
                selected_device = device
                break

        if selected_device is None:
            return Response(
                {"device_id": ["This Spotify device is not currently available."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if selected_device.get("is_restricted") is True:
            return Response(
                {"device_id": ["Spotify does not permit API control of this device."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device_name = selected_device.get("name")
        safe_device_name = (
            device_name if isinstance(device_name, str) else "Spotify device"
        )

        try:
            transfer_response = httpx.put(
                "https://api.spotify.com/v1/me/player",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "device_ids": [requested_device_id],
                    "play": False,
                },
                timeout=15.0,
            )
            transfer_response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 403:
                return Response(
                    {
                        "detail": (
                            "Spotify could not control this device. "
                            "Confirm that the account has Premium."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return Response(
                {"detail": "Spotify could not select this device."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except httpx.HTTPError:
            return Response(
                {"detail": "Spotify could not be reached."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        game = get_object_or_404(
            Game,
            pk=game_id,
            host=request.user,
        )

        Game.objects.filter(pk=game.pk).update(
            spotify_device_id=requested_device_id,
            spotify_device_name=safe_device_name,
        )

        return Response(
            {
                "selected": True,
                "device": {
                    "id": requested_device_id,
                    "name": safe_device_name,
                    "type": selected_device.get("type"),
                    "is_active": selected_device.get(
                        "is_active",
                        False,
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )


class StartTrackPlaybackView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        session = cast(
            SessionBase,
            getattr(request, "session"),
        )

        # The Celery worker needs this key to retrieve the host's
        # Spotify tokens from Django's database-backed session.
        if session.session_key is None:
            session.save()

        session_key = session.session_key

        if session_key is None:
            return Response(
                {
                    "detail": "The host session could not be saved.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": "Spotify has not been connected.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except SpotifyServiceError:
            return Response(
                {
                    "detail": "Spotify authentication failed.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "track",
                    "team",
                    "genre",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": "The game is not in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status not in (
                GameTurn.Status.TRACK_READY,
                GameTurn.Status.AWAITING_ANSWER,
            ):
                return Response(
                    {
                        "detail": (
                            "A prepared track can only be played "
                            "before the answer is revealed."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            track = turn.track

            if track is None:
                return Response(
                    {
                        "detail": (
                            "This turn does not have a prepared track."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            genre = turn.genre

            if genre is None:
                return Response(
                    {
                        "detail": "This turn does not have a genre.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            device_id = game.spotify_device_id.strip()

            if not device_id:
                return Response(
                    {
                        "detail": (
                            "Select a central Spotify device "
                            "before playback."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            playback_start_ms = int(game.default_playback_start_ms)

            def attempt_playback(target_device_id: str) -> None:
                spotify_response = httpx.put(
                    "https://api.spotify.com/v1/me/player/play",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    params={
                        "device_id": target_device_id,
                    },
                    json={
                        "uris": [track.spotify_uri],
                        "position_ms": playback_start_ms,
                    },
                    timeout=15.0,
                )
                spotify_response.raise_for_status()

            try:
                attempt_playback(device_id)

            except httpx.HTTPStatusError as error:
                spotify_status = error.response.status_code

                if spotify_status == 404:
                    try:
                        replacement_device = _find_replacement_spotify_device(
                            access_token=access_token,
                            saved_device_id=device_id,
                            saved_device_name=game.spotify_device_name,
                        )
                    except httpx.HTTPError:
                        replacement_device = None

                    if replacement_device is None:
                        return Response(
                            {
                                "detail": (
                                    "The selected Spotify device is "
                                    "unavailable. Open Spotify and select "
                                    "the device again."
                                )
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    replacement_device_id = cast(
                        str,
                        replacement_device["id"],
                    )
                    replacement_device_name = cast(
                        str,
                        replacement_device.get("name") or game.spotify_device_name,
                    )

                    try:
                        attempt_playback(replacement_device_id)
                    except httpx.HTTPStatusError as retry_error:
                        retry_status = retry_error.response.status_code

                        if retry_status == 403:
                            return Response(
                                {
                                    "detail": (
                                        "Spotify refused playback. Confirm "
                                        "that the account has Premium and the "
                                        "device is not restricted."
                                    )
                                },
                                status=status.HTTP_403_FORBIDDEN,
                            )

                        if retry_status == 429:
                            return Response(
                                {
                                    "detail": (
                                        "Spotify's rate limit was reached. "
                                        "Try again shortly."
                                    )
                                },
                                status=status.HTTP_429_TOO_MANY_REQUESTS,
                            )

                        return Response(
                            {
                                "detail": (
                                    "The selected Spotify device is "
                                    "unavailable. Open Spotify and select "
                                    "the device again."
                                )
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    except httpx.HTTPError:
                        return Response(
                            {
                                "detail": "Spotify could not be reached.",
                            },
                            status=status.HTTP_502_BAD_GATEWAY,
                        )

                    device_id = replacement_device_id
                    game.spotify_device_id = replacement_device_id
                    game.spotify_device_name = replacement_device_name
                    game.save(
                        update_fields=[
                            "spotify_device_id",
                            "spotify_device_name",
                        ]
                    )

                elif spotify_status == 403:
                    return Response(
                        {
                            "detail": (
                                "Spotify refused playback. Confirm "
                                "that the account has Premium and the "
                                "device is not restricted."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                elif spotify_status == 429:
                    return Response(
                        {
                            "detail": (
                                "Spotify's rate limit was reached. "
                                "Try again shortly."
                            )
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                else:
                    return Response(
                        {
                            "detail": "Spotify could not start playback.",
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

            except httpx.HTTPError:
                return Response(
                    {
                        "detail": "Spotify could not be reached.",
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            playback_started_at = timezone.now()
            clip_ends_at = playback_started_at + timedelta(
                seconds=PLAYBACK_CLIP_DURATION_SECONDS
            )

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                status=GameTurn.Status.PLAYING,
                playback_started_at=playback_started_at,
                playback_stopped_at=None,
            )

            updated_turn = (
                GameTurn.objects.select_related(
                    "track",
                    "team",
                    "genre",
                ).get(pk=turn.pk)
            )

            playback_event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "playback_duration_seconds": PLAYBACK_CLIP_DURATION_SECONDS,
                "playback_started_at": (
                    playback_started_at.isoformat()
                ),
                "clip_ends_at": clip_ends_at.isoformat(),
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
                },
                "genre": {
                    "id": str(genre.pk),
                    "name": genre.name,
                    "color": genre.color,
                },
            }

            pause_task = cast(
                Task,
                stop_spotify_playback,
            )

            # Register this first because stopping Spotify after the clip
            # duration is more important than sending the WebSocket event.
            transaction.on_commit(
                lambda: pause_task.apply_async(
                    args=(
                        str(turn.pk),
                        session_key,
                    ),
                    countdown=PLAYBACK_CLIP_DURATION_SECONDS,
                )
            )

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "playback.started",
                    playback_event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "started": True,
                "clip_duration_seconds": PLAYBACK_CLIP_DURATION_SECONDS,
                "playback_started_at": playback_started_at,
                "clip_ends_at": clip_ends_at,
                "device": {
                    "id": device_id,
                    "name": game.spotify_device_name,
                },
                "turn": GameTurnSerializer(updated_turn).data,
                # Only the authenticated host receives the answer.
                "track": HostTrackSerializer(track).data,
            },
            status=status.HTTP_200_OK,
        )


class StopTrackPlaybackView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(
        self,
        request,
        game_id,
        turn_id,
    ):
        session = cast(
            SessionBase,
            getattr(request, "session"),
        )

        try:
            access_token = get_valid_access_token(session, user_id=request.user.pk)
        except SpotifyNotConnectedError:
            return Response(
                {
                    "detail": "Spotify has not been connected.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except SpotifyServiceError:
            return Response(
                {
                    "detail": "Spotify authentication failed.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "team",
                    "genre",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": "The game is not in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status != GameTurn.Status.PLAYING:
                return Response(
                    {
                        "detail": (
                            "This turn is not currently playing."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            device_id = game.spotify_device_id.strip()

            if not device_id:
                return Response(
                    {
                        "detail": (
                            "No central Spotify device has "
                            "been selected."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            try:
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

            except httpx.HTTPStatusError as error:
                spotify_status = error.response.status_code

                if spotify_status == 404:
                    return Response(
                        {
                            "detail": (
                                "The selected Spotify device is "
                                "unavailable or there is no active "
                                "playback."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if spotify_status == 403:
                    return Response(
                        {
                            "detail": (
                                "Spotify refused the pause request. "
                                "Confirm that the account has Premium."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if spotify_status == 429:
                    return Response(
                        {
                            "detail": (
                                "Spotify's rate limit was reached. "
                                "Try again shortly."
                            )
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                return Response(
                    {
                        "detail": (
                            "Spotify could not stop playback."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            except httpx.HTTPError:
                return Response(
                    {
                        "detail": "Spotify could not be reached.",
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            playback_stopped_at = timezone.now()

            updated_count = GameTurn.objects.filter(
                pk=turn.pk,
                status=GameTurn.Status.PLAYING,
            ).update(
                status=GameTurn.Status.AWAITING_ANSWER,
                playback_stopped_at=playback_stopped_at,
            )

            # The Celery task might have stopped this turn while
            # the manual stop request was being processed.
            if updated_count == 0:
                return Response(
                    {
                        "detail": (
                            "This turn is no longer playing."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            updated_turn = (
                GameTurn.objects.select_related(
                    "team",
                    "genre",
                ).get(pk=turn.pk)
            )

            genre = updated_turn.genre

            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "reason": "admin_manual",
                "playback_stopped_at": (
                    playback_stopped_at.isoformat()
                ),
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
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

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "playback.stopped",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "stopped": True,
                "reason": "admin_manual",
                "playback_stopped_at": playback_stopped_at,
                "turn": GameTurnSerializer(updated_turn).data,
            },
            status=status.HTTP_200_OK,
        )


class RevealAnswerView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "track",
                    "team",
                    "genre",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {"detail": "The game is not in progress."},
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status == GameTurn.Status.ANSWER_REVEALED:
                track = turn.track

                if track is None:
                    return Response(
                        {"detail": "This turn does not have a track."},
                        status=status.HTTP_409_CONFLICT,
                    )

                return Response(
                    {
                        "revealed": True,
                        "detail": "The answer has already been revealed.",
                        "turn": GameTurnSerializer(turn).data,
                        "answer": HostTrackSerializer(track).data,
                    },
                    status=status.HTTP_200_OK,
                )

            if turn.status != GameTurn.Status.AWAITING_ANSWER:
                return Response(
                    {
                        "detail": (
                            "Playback must stop before the answer can be revealed."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            track = turn.track

            if track is None:
                return Response(
                    {"detail": "This turn does not have a track."},
                    status=status.HTTP_409_CONFLICT,
                )

            answer_revealed_at = timezone.now()

            GameTurn.objects.filter(pk=turn.pk).update(
                status=GameTurn.Status.ANSWER_REVEALED,
                answer_revealed_at=answer_revealed_at,
            )

            updated_turn = GameTurn.objects.select_related(
                "track",
                "team",
                "genre",
            ).get(pk=turn.pk)

            track = updated_turn.track

            if track is None:
                return Response(
                    {
                        "detail": "This turn does not have a track.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            genre = updated_turn.genre

            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "answer_revealed_at": answer_revealed_at.isoformat(),
                "team": {
                    "id": str(updated_turn.team.pk),
                    "name": updated_turn.team.name,
                    "color": updated_turn.team.color,
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
                "answer": {
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "artwork_url": track.artwork_url,
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "answer.revealed",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "revealed": True,
                "answer_revealed_at": answer_revealed_at,
                "turn": GameTurnSerializer(updated_turn).data,
                "answer": HostTrackSerializer(track).data,
            },
            status=status.HTTP_200_OK,
        )


class AwardScoreView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        serializer = AwardScoreSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        validated_data = cast(
            dict[str, object],
            serializer.validated_data,
        )

        song_title_correct = cast(
            bool,
            validated_data["song_title_correct"],
        )
        artist_correct = cast(
            bool,
            validated_data["artist_correct"],
        )

        if song_title_correct and artist_correct:
            points = 3
        elif song_title_correct or artist_correct:
            points = 1
        else:
            points = 0

        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            turn = get_object_or_404(
                GameTurn.objects.select_for_update().select_related(
                    "team",
                    "genre",
                    "track",
                ),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": (
                            "The game is not currently in progress."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status != GameTurn.Status.ANSWER_REVEALED:
                return Response(
                    {
                        "detail": (
                            "The answer must be revealed before "
                            "points can be awarded."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if ScoreEvent.objects.filter(turn=turn).exists():
                return Response(
                    {
                        "detail": (
                            "A score has already been recorded "
                            "for this turn."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            team = turn.team

            score_event = ScoreEvent.objects.create(
                game=game,
                turn=turn,
                team=team,
                song_title_correct=song_title_correct,
                artist_correct=artist_correct,
                points=points,
                awarded_by=request.user,
            )

            completed_at = timezone.now()

            GameTurn.objects.filter(
                pk=turn.pk,
            ).update(
                status=GameTurn.Status.COMPLETED,
                completed_at=completed_at,
            )

            team_total_result = ScoreEvent.objects.filter(
                game=game,
                team=team,
            ).aggregate(
                total=Sum("points"),
            )

            team_total = team_total_result["total"] or 0

            updated_turn = (
                GameTurn.objects.select_related(
                    "team",
                    "genre",
                    "track",
                ).get(pk=turn.pk)
            )

            event_data = {
                "game_id": str(game.pk),
                "turn_id": str(updated_turn.pk),
                "turn_status": updated_turn.status,
                "completed_at": completed_at.isoformat(),
                "team": {
                    "id": str(team.pk),
                    "name": team.name,
                    "color": team.color,
                },
                "result": {
                    "song_title_correct": (
                        score_event.song_title_correct
                    ),
                    "artist_correct": (
                        score_event.artist_correct
                    ),
                    "points": score_event.points,
                },
                "team_total_points": team_total,
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "score.awarded",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "awarded": True,
                "result": {
                    "song_title_correct": song_title_correct,
                    "artist_correct": artist_correct,
                    "points_awarded": points,
                },
                "score_event": ScoreEventSerializer(
                    score_event
                ).data,
                "team_total": team_total,
                "turn": GameTurnSerializer(
                    updated_turn
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )
    


class AdvanceTurnView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id, turn_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            completed_turn = get_object_or_404(
                GameTurn.objects.select_for_update(),
                pk=turn_id,
                game=game,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": "The game is not in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if completed_turn.status != GameTurn.Status.COMPLETED:
                return Response(
                    {
                        "detail": (
                            "The current turn must be completed "
                            "before advancing."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if GameTurn.objects.filter(
                game=game,
                status=GameTurn.Status.ACTIVE,
            ).exists():
                return Response(
                    {
                        "detail": "Another turn is already active.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            next_turn = (
                GameTurn.objects.select_for_update()
                .filter(
                    game=game,
                    round_number=completed_turn.round_number,
                    turn_position__gt=(
                        completed_turn.turn_position
                    ),
                    status=GameTurn.Status.WAITING,
                )
                .order_by("turn_position")
                .first()
            )

            if next_turn is None:
                round_event_data = {
                    "game_id": str(game.pk),
                    "round_number": (
                        completed_turn.round_number
                    ),
                    "round_completed": True,
                    "completed_turn_id": str(
                        completed_turn.pk
                    ),
                }

                transaction.on_commit(
                    partial(
                        broadcast_game_event,
                        game.join_token,
                        "round.completed",
                        round_event_data,
                    ),
                    robust=True,
                )

                return Response(
                    {
                        "advanced": False,
                        "round_completed": True,
                        "round_number": (
                            completed_turn.round_number
                        ),
                        "detail": (
                            "Every team has completed this round."
                        ),
                        "next_turn": None,
                    },
                    status=status.HTTP_200_OK,
                )

            started_at = timezone.now()

            GameTurn.objects.filter(
                pk=next_turn.pk,
            ).update(
                status=GameTurn.Status.ACTIVE,
                started_at=started_at,
            )

            updated_turn = (
                GameTurn.objects.select_related(
                    "team",
                    "genre",
                    "track",
                ).get(pk=next_turn.pk)
            )

            turn_event_data = {
                "game_id": str(game.pk),
                "previous_turn_id": str(
                    completed_turn.pk
                ),
                "round_number": (
                    updated_turn.round_number
                ),
                "active_turn": {
                    "id": str(updated_turn.pk),
                    "round_number": (
                        updated_turn.round_number
                    ),
                    "turn_position": (
                        updated_turn.turn_position
                    ),
                    "status": updated_turn.status,
                    "started_at": started_at.isoformat(),
                    "team": {
                        "id": str(updated_turn.team.pk),
                        "name": updated_turn.team.name,
                        "color": updated_turn.team.color,
                    },
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "turn.advanced",
                    turn_event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "advanced": True,
                "round_completed": False,
                "active_turn": GameTurnSerializer(
                    updated_turn
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class PublicLeaderboardView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, join_token):
        game = get_object_or_404(
            Game,
            join_token=join_token,
        )

        teams = Team.objects.filter(
            game=game,
        ).order_by("position")

        leaderboard_entries = []

        for team in teams:
            score_result = ScoreEvent.objects.filter(
                game=game,
                team=team,
            ).aggregate(total=Sum("points"))

            total_score = score_result["total"] or 0

            player_count = Player.objects.filter(
                game=game,
                team=team,
            ).count()

            leaderboard_entries.append(
                {
                    "team_id": team.pk,
                    "team_name": team.name,
                    "color": team.color,
                    "team_position": team.position,
                    "player_count": player_count,
                    "score": total_score,
                }
            )

        leaderboard_entries.sort(
            key=lambda entry: (
                -int(cast(int, entry["score"])),
                int(cast(int, entry["team_position"])),
            )
        )

        previous_score = None
        current_rank = 0

        for index, entry in enumerate(
            leaderboard_entries,
            start=1,
        ):
            score = entry["score"]

            if score != previous_score:
                current_rank = index

            entry["rank"] = current_rank
            previous_score = score

        return Response(
            {
                "game": {
                    "join_token": game.join_token,
                    "name": game.name,
                    "status": game.status,
                    "current_round": game.current_round,
                },
                "leaderboard": leaderboard_entries,
            },
            status=status.HTTP_200_OK,
        )


class StartNextRoundView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.status != Game.Status.IN_PROGRESS:
                return Response(
                    {
                        "detail": "The game is not in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            current_round = game.current_round

            current_turns = list(
                GameTurn.objects.select_for_update()
                .filter(
                    game=game,
                    round_number=current_round,
                )
                .order_by("turn_position")
            )

            if not current_turns:
                return Response(
                    {
                        "detail": (
                            "The current round does not contain "
                            "any turns."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            incomplete_turns_exist = any(
                turn.status != GameTurn.Status.COMPLETED
                for turn in current_turns
            )

            if incomplete_turns_exist:
                return Response(
                    {
                        "detail": (
                            "Every team must complete the current "
                            "round before another round can start."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if current_round >= game.rounds_per_team:
                return Response(
                    {
                        "detail": (
                            "The configured round limit has been reached. "
                            "Finish the game to show the final results."
                        ),
                        "round_limit_reached": True,
                        "current_round": current_round,
                        "rounds_per_team": game.rounds_per_team,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            teams = list(
                Team.objects.filter(
                    game=game,
                ).order_by("position")
            )

            if not teams:
                return Response(
                    {
                        "detail": "The game does not have any teams.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            next_round = current_round + 1

            secrets.SystemRandom().shuffle(teams)

            started_at = timezone.now()

            new_turns = [
                GameTurn(
                    game=game,
                    team=team,
                    round_number=next_round,
                    turn_position=index,
                    status=(
                        GameTurn.Status.ACTIVE
                        if index == 1
                        else GameTurn.Status.WAITING
                    ),
                    started_at=(
                        started_at
                        if index == 1
                        else None
                    ),
                )
                for index, team in enumerate(
                    teams,
                    start=1,
                )
            ]

            GameTurn.objects.bulk_create(new_turns)

            game.current_round = next_round
            game.save(
                update_fields=[
                    "current_round",
                    "updated_at",
                ]
            )

            active_turn = (
                GameTurn.objects.select_related(
                    "team",
                ).get(
                    game=game,
                    round_number=next_round,
                    status=GameTurn.Status.ACTIVE,
                )
            )

            created_turns = list(
                GameTurn.objects.select_related(
                    "team",
                )
                .filter(
                    game=game,
                    round_number=next_round,
                )
                .order_by("turn_position")
            )

            round_event_data = {
                "game_id": str(game.pk),
                "round_number": next_round,
                "active_turn": {
                    "id": str(active_turn.pk),
                    "round_number": (
                        active_turn.round_number
                    ),
                    "turn_position": (
                        active_turn.turn_position
                    ),
                    "status": active_turn.status,
                    "started_at": (
                        active_turn.started_at.isoformat()
                        if active_turn.started_at is not None
                        else None
                    ),
                    "team": {
                        "id": str(active_turn.team.pk),
                        "name": active_turn.team.name,
                        "color": active_turn.team.color,
                    },
                },
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "round.started",
                    round_event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "started": True,
                "round_number": next_round,
                "game": GameSerializer(game).data,
                "active_turn": GameTurnSerializer(
                    active_turn
                ).data,
                "turns": GameTurnSerializer(
                    created_turns,
                    many=True,
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class FinishGameView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if game.status == Game.Status.FINISHED:
                return Response(
                    {
                        "detail": "This game has already finished.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if game.status not in (
                Game.Status.IN_PROGRESS,
                Game.Status.PAUSED,
            ):
                return Response(
                    {
                        "detail": (
                            "Only a game that has started can "
                            "be finished."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if GameTurn.objects.filter(
                game=game,
                status=GameTurn.Status.PLAYING,
            ).exists():
                return Response(
                    {
                        "detail": (
                            "Stop Spotify playback before "
                            "finishing the game."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            finished_at = timezone.now()

            game.status = Game.Status.FINISHED
            game.registration_open = False
            game.finished_at = finished_at
            game.save(
                update_fields=[
                    "status",
                    "registration_open",
                    "finished_at",
                    "updated_at",
                ]
            )

            teams = list(
                Team.objects.filter(
                    game=game,
                ).order_by("position")
            )

            standings: list[dict[str, object]] = []

            for team in teams:
                score_result = ScoreEvent.objects.filter(
                    game=game,
                    team=team,
                ).aggregate(
                    total=Sum("points"),
                )

                total_score = score_result["total"] or 0

                standings.append(
                    {
                        # Strings are safe for both DRF JSON responses
                        # and the Channels Redis serializer.
                        "team_id": str(team.pk),
                        "team_name": team.name,
                        "color": team.color,
                        "score": total_score,
                        "team_position": team.position,
                    }
                )

            standings.sort(
                key=lambda entry: (
                    -cast(int, entry["score"]),
                    cast(int, entry["team_position"]),
                )
            )

            previous_score: int | None = None
            current_rank = 0

            for index, entry in enumerate(
                standings,
                start=1,
            ):
                entry_score = cast(
                    int,
                    entry["score"],
                )

                if entry_score != previous_score:
                    current_rank = index

                entry["rank"] = current_rank
                previous_score = entry_score

            winning_score = (
                cast(int, standings[0]["score"])
                if standings
                else 0
            )

            winners: list[dict[str, object]] = [
                {
                    "team_id": entry["team_id"],
                    "team_name": entry["team_name"],
                    "color": entry["color"],
                    "score": entry["score"],
                    "rank": entry["rank"],
                }
                for entry in standings
                if cast(int, entry["score"]) == winning_score
            ]

            event_data = {
                "game_id": str(game.pk),
                "status": game.status,
                "registration_open": game.registration_open,
                "finished_at": finished_at.isoformat(),
                "winners": winners,
                "standings": standings,
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "game.finished",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "finished": True,
                "finished_at": finished_at,
                "game": GameSerializer(game).data,
                "winners": winners,
                "standings": standings,
            },
            status=status.HTTP_200_OK,
        )


class RestartGameView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, game_id):
        with transaction.atomic():
            game = get_object_or_404(
                Game.objects.select_for_update(),
                pk=game_id,
                host=request.user,
            )

            if GameTurn.objects.filter(
                game=game,
                status=GameTurn.Status.PLAYING,
            ).exists():
                return Response(
                    {
                        "detail": (
                            "Stop Spotify playback before restarting the game."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            Player.objects.filter(game=game).update(team=None)
            GameTurn.objects.filter(game=game).delete()
            Team.objects.filter(game=game).delete()

            game.status = Game.Status.LOBBY_OPEN
            game.registration_open = True
            game.current_round = 0
            game.finished_at = None
            game.save(
                update_fields=[
                    "status",
                    "registration_open",
                    "current_round",
                    "finished_at",
                    "updated_at",
                ]
            )

            player_count = Player.objects.filter(game=game).count()
            event_data = {
                "game_id": str(game.pk),
                "status": game.status,
                "registration_open": game.registration_open,
                "current_round": game.current_round,
                "finished_at": None,
                "player_count": player_count,
            }

            transaction.on_commit(
                partial(
                    broadcast_game_event,
                    game.join_token,
                    "game.restarted",
                    event_data,
                ),
                robust=True,
            )

        return Response(
            {
                "restarted": True,
                "game": GameSerializer(game).data,
                "player_count": player_count,
            },
            status=status.HTTP_200_OK,
        )


class GameStateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, join_token):
        game = get_object_or_404(
            Game,
            join_token=join_token,
        )

        teams = list(
            Team.objects.filter(game=game)
            .select_related("leader")
            .order_by("position")
        )
        team_members: dict[int, list[dict[str, str]]] = {}

        for player in (
            Player.objects.filter(
                game=game,
                team__isnull=False,
            )
            .order_by("display_name")
        ):
            if player.team_id is None:
                continue

            team_members.setdefault(
                player.team_id,
                [],
            ).append(
                {
                    "id": str(player.pk),
                    "display_name": player.display_name,
                }
            )

        teams_data: list[dict[str, object]] = []

        for team in teams:
            leader = team.leader

            score_result = ScoreEvent.objects.filter(
                game=game,
                team=team,
            ).aggregate(
                total=Sum("points"),
            )

            total_points = score_result["total"] or 0

            teams_data.append(
                {
                    "id": str(team.pk),
                    "name": team.name,
                    "color": team.color,
                    "position": team.position,
                    "leader": (
                        {
                            "id": str(leader.pk),
                            "display_name": leader.display_name,
                        }
                        if leader is not None
                        else None
                    ),
                    "players": team_members.get(team.pk, []),
                    "total_points": total_points,
                }
            )

        teams_data.sort(
            key=lambda team_data: (
                -cast(int, team_data["total_points"]),
                cast(int, team_data["position"]),
            )
        )

        previous_score: int | None = None
        current_rank = 0

        for index, team_data in enumerate(
            teams_data,
            start=1,
        ):
            score = cast(
                int,
                team_data["total_points"],
            )

            if score != previous_score:
                current_rank = index

            team_data["rank"] = current_rank
            previous_score = score

        current_turn = (
            GameTurn.objects.filter(
                game=game,
                round_number=game.current_round,
            )
            .exclude(
                status=GameTurn.Status.WAITING,
            )
            .select_related(
                "team",
                "genre",
                "track",
            )
            .order_by("-turn_position")
            .first()
        )

        current_turn_data: dict[str, object] | None = None

        if current_turn is not None:
            genre = (
                current_turn.genre
                if current_turn.status != GameTurn.Status.ACTIVE
                else None
            )

            current_turn_data = {
                "id": str(current_turn.pk),
                "round_number": current_turn.round_number,
                "turn_position": current_turn.turn_position,
                "status": current_turn.status,
                "team": {
                    "id": str(current_turn.team.pk),
                    "name": current_turn.team.name,
                    "color": current_turn.team.color,
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
                "track_ready": current_turn.track is not None,
            }

            # Never reveal the answer until the admin has revealed it.
            if current_turn.status in (
                GameTurn.Status.ANSWER_REVEALED,
                GameTurn.Status.COMPLETED,
            ):
                track = current_turn.track

                if track is not None:
                    current_turn_data["answer"] = {
                        "title": track.title,
                        "artist": track.artist,
                        "album": track.album,
                        "artwork_url": track.artwork_url,
                    }

        return Response(
            {
                "game": {
                    "id": str(game.pk),
                    "join_token": str(game.join_token),
                    "name": game.name,
                    "status": game.status,
                    "registration_open": game.registration_open,
                    "number_of_teams": game.number_of_teams,
                    "rounds_per_team": game.rounds_per_team,
                    "current_round": game.current_round,
                    "finished_at": (
                        game.finished_at.isoformat()
                        if game.finished_at is not None
                        else None
                    ),
                },
                "current_turn": current_turn_data,
                "standings": teams_data,
            },
            status=status.HTTP_200_OK,
        )
