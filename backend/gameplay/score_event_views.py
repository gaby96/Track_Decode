from functools import partial
from typing import cast

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from games.models import Game
from games.realtime import broadcast_game_event
from games.serializers import (
    AwardScoreSerializer,
    GameTurnSerializer,
    ScoreEventSerializer,
)
from lobby.models import Player, Team
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from gameplay.models import GameTurn, ScoreEvent


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
                    {"detail": ("The game is not currently in progress.")},
                    status=status.HTTP_409_CONFLICT,
                )

            if turn.status != GameTurn.Status.ANSWER_REVEALED:
                return Response(
                    {
                        "detail": (
                            "The answer must be revealed before points can be awarded."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if ScoreEvent.objects.filter(turn=turn).exists():
                return Response(
                    {"detail": ("A score has already been recorded for this turn.")},
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

            updated_turn = GameTurn.objects.select_related(
                "team",
                "genre",
                "track",
            ).get(pk=turn.pk)

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
                    "song_title_correct": (score_event.song_title_correct),
                    "artist_correct": (score_event.artist_correct),
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
                "score_event": ScoreEventSerializer(score_event).data,
                "team_total": team_total,
                "turn": GameTurnSerializer(updated_turn).data,
            },
            status=status.HTTP_201_CREATED,
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


