from rest_framework import serializers

from gameplay.serializers import (
    AwardScoreSerializer,
    GameTurnSerializer,
    ScoreEventSerializer,
)
from lobby.models import Player
from lobby.serializers import (
    LeaderVoteSubmitSerializer,
    PlayerJoinSerializer,
    PlayerSessionSerializer,
    PublicPlayerSerializer,
    TeamSerializer,
)
from music.serializers import GenreSerializer, HostTrackSerializer
from spotify.serializers import SpotifyDeviceSelectionSerializer

from .models import Game


class GameSerializer(serializers.ModelSerializer):
    host_username = serializers.CharField(source="host.username", read_only=True)

    class Meta:
        model = Game
        fields = (
            "id",
            "join_token",
            "join_code",
            "name",
            "number_of_teams",
            "rounds_per_team",
            "status",
            "registration_open",
            "current_round",
            "host_username",
            "spotify_device_id",
            "spotify_device_name",
            "created_at",
            "updated_at",
            "finished_at",
        )
        read_only_fields = (
            "id",
            "join_token",
            "join_code",
            "status",
            "registration_open",
            "current_round",
            "host_username",
            "created_at",
            "updated_at",
        )


class PublicGameSerializer(serializers.ModelSerializer):
    player_count = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = (
            "join_token",
            "join_code",
            "name",
            "number_of_teams",
            "rounds_per_team",
            "status",
            "registration_open",
            "player_count",
        )
        read_only_fields = fields

    def get_player_count(self, game: Game) -> int:
        return Player.objects.filter(game=game).count()


class GameRoundsPerTeamUpdateSerializer(serializers.Serializer):
    rounds_per_team = serializers.IntegerField(min_value=1)


__all__ = [
    "AwardScoreSerializer",
    "GameRoundsPerTeamUpdateSerializer",
    "GameSerializer",
    "GameTurnSerializer",
    "GenreSerializer",
    "HostTrackSerializer",
    "LeaderVoteSubmitSerializer",
    "PlayerJoinSerializer",
    "PlayerSessionSerializer",
    "PublicGameSerializer",
    "PublicPlayerSerializer",
    "ScoreEventSerializer",
    "SpotifyDeviceSelectionSerializer",
    "TeamSerializer",
]
