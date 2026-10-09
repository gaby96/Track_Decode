from rest_framework import serializers

from .models import GameTurn, ScoreEvent


class GameTurnSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    genre_name = serializers.CharField(
        source="genre.name", read_only=True, allow_null=True
    )

    class Meta:
        model = GameTurn
        fields = (
            "id",
            "round_number",
            "turn_position",
            "team",
            "team_name",
            "genre",
            "genre_name",
            "status",
            "started_at",
            "completed_at",
        )
        read_only_fields = fields


class AwardScoreSerializer(serializers.Serializer):
    song_title_correct = serializers.BooleanField()
    artist_correct = serializers.BooleanField()


class ScoreEventSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    awarded_by_username = serializers.CharField(
        source="awarded_by.username", read_only=True
    )

    class Meta:
        model = ScoreEvent
        fields = (
            "id",
            "turn",
            "team",
            "team_name",
            "song_title_correct",
            "artist_correct",
            "points",
            "awarded_by_username",
            "created_at",
        )
        read_only_fields = fields
