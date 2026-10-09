import hashlib
import random
from functools import partial
from typing import cast
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from games.constants import STRING_ERROR_RESPONSES
from games.models import Game
from games.realtime import broadcast_game_event
from games.serializers import (
    GameSerializer,
    PlayerSessionSerializer,
    PublicPlayerSerializer,
    TeamSerializer,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from lobby.models import LeaderVote, Player, Team


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

        session_token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()

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
                        "detail": ("The player has not been assigned to a team."),
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
                            "The selected candidate is not a member of your team."
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
                "voting_complete": (votes_submitted >= team_player_count),
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
                "detail": ("Leader vote submitted."),
                "team_id": str(team.pk),
                "votes_submitted": votes_submitted,
                "team_player_count": team_player_count,
                "voting_complete": (votes_submitted >= team_player_count),
            },
            status=(status.HTTP_201_CREATED),
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
                {"detail": STRING_ERROR_RESPONSES['invalid_player_session']},
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

                winning_id = random.SystemRandom().choice(winning_ids)

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
            Team.objects.filter(game=game).select_related("leader").order_by("position")
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


