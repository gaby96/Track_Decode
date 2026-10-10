from rest_framework import serializers

from .models import Player, Team


class PlayerJoinSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=50, trim_whitespace=True)

    def validate_display_name(self, value):
        normalized_name = " ".join(value.split())
        if not normalized_name:
            raise serializers.ValidationError("Enter a valid display name.")
        return normalized_name


class PublicPlayerSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )

    class Meta:
        model = Player
        fields = (
            "id",
            "display_name",
            "team",
            "team_name",
            "is_connected",
            "joined_at",
        )
        read_only_fields = fields


class TeamSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ("id", "name", "color", "position", "leader", "players")
        read_only_fields = fields

    def get_players(self, team: Team):
        players = Player.objects.filter(team=team).order_by("joined_at")
        return PublicPlayerSerializer(players, many=True).data


class LeaderVoteSubmitSerializer(serializers.Serializer):
    candidate_id = serializers.UUIDField()
