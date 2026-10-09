import random
from functools import partial
from typing import cast

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from gameplay.models import GameTurn, ScoreEvent
from lobby.models import Player, Team
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import STRING_ERROR_RESPONSES
from .models import Game
from .realtime import broadcast_game_event
from .serializers import (
    GameRoundsPerTeamUpdateSerializer,
    GameSerializer,
    GameTurnSerializer,
    PublicGameSerializer,
)


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
                game.status
                in (
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
                Team.objects.select_for_update().filter(game=game).order_by("position")
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

            random.SystemRandom().shuffle(teams)
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
                        "detail": STRING_ERROR_RESPONSES["game_not_in_progress"],
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
                    {"detail": ("The current round does not contain any turns.")},
                    status=status.HTTP_409_CONFLICT,
                )

            incomplete_turns_exist = any(
                turn.status != GameTurn.Status.COMPLETED for turn in current_turns
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

            random.SystemRandom().shuffle(teams)

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
                    started_at=(started_at if index == 1 else None),
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

            active_turn = GameTurn.objects.select_related(
                "team",
            ).get(
                game=game,
                round_number=next_round,
                status=GameTurn.Status.ACTIVE,
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
                    "round_number": (active_turn.round_number),
                    "turn_position": (active_turn.turn_position),
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
                "active_turn": GameTurnSerializer(active_turn).data,
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
                    {"detail": ("Only a game that has started can be finished.")},
                    status=status.HTTP_409_CONFLICT,
                )

            if GameTurn.objects.filter(
                game=game,
                status=GameTurn.Status.PLAYING,
            ).exists():
                return Response(
                    {"detail": ("Stop Spotify playback before finishing the game.")},
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

            winning_score = cast(int, standings[0]["score"]) if standings else 0

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
                    {"detail": ("Stop Spotify playback before restarting the game.")},
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

    def get(self, request, join_token):
        game = get_object_or_404(
            Game,
            join_token=join_token,
        )

        teams = list(
            Team.objects.filter(game=game)
            .select_related("leader")
            .annotate(
                total_points=Sum(
                    "score_events__points",
                    filter=Q(score_events__game=game),
                )
            )
            .order_by("position")
        )
        team_members: dict[int, list[dict[str, str]]] = {}

        for player in Player.objects.filter(
            game=game,
            team__isnull=False,
        ).order_by("display_name"):
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
            total_points = getattr(team, "total_points", None) or 0

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

