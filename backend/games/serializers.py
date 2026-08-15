from rest_framework import serializers

from .models import Game, GameTurn, Genre, Player, ScoreEvent, Team, Track


class GameSerializer(serializers.ModelSerializer):
    host_username = serializers.CharField(
        source="host.username",
        read_only=True,
    )

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
            "finished_at"
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


class PlayerJoinSerializer(serializers.Serializer):
    display_name = serializers.CharField(
        max_length=50,
        trim_whitespace=True,
    )

    def validate_display_name(self, value):
        normalized_name = " ".join(value.split())

        if not normalized_name:
            raise serializers.ValidationError("Enter a valid display name.")

        return normalized_name


class PublicPlayerSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(
        source="team.name",
        read_only=True,
        allow_null=True,
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
        fields = (
            "id",
            "name",
            "color",
            "position",
            "leader",
            "players",
        )
        read_only_fields = fields

    def get_players(self, team: Team):
        players = Player.objects.filter(team=team).order_by("joined_at")
        return PublicPlayerSerializer(players, many=True).data


class LeaderVoteSubmitSerializer(serializers.Serializer):
    session_token = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    candidate_id = serializers.UUIDField()

class PlayerSessionSerializer(serializers.Serializer):
    session_token = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )


class GameRoundsPerTeamUpdateSerializer(serializers.Serializer):
    rounds_per_team = serializers.IntegerField(
        min_value=1,
    )

class GameTurnSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(
        source="team.name",
        read_only=True,
    )
    genre_name = serializers.CharField(
        source="genre.name",
        read_only=True,
        allow_null=True,
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

class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = (
            "id",
            "name",
            "color",
        )
        read_only_fields = fields


class HostTrackSerializer(serializers.ModelSerializer):
    spotify_url = serializers.SerializerMethodField()

    class Meta:
        model = Track
        fields = (
            "id",
            "spotify_track_id",
            "spotify_uri",
            "spotify_url",
            "title",
            "artist",
            "album",
            "artwork_url",
            "duration_ms",
            "is_explicit",
        )
        read_only_fields = fields

    def get_spotify_url(self, track: Track) -> str:
        return (
            "https://open.spotify.com/track/"
            f"{track.spotify_track_id}"
        )

class SpotifyDeviceSelectionSerializer(serializers.Serializer):
    device_id = serializers.CharField(
        max_length=255,
        trim_whitespace=True,
    )

class AwardScoreSerializer(serializers.Serializer):
    song_title_correct = serializers.BooleanField()
    artist_correct = serializers.BooleanField()


class ScoreEventSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(
        source="team.name",
        read_only=True,
    )
    awarded_by_username = serializers.CharField(
        source="awarded_by.username",
        read_only=True,
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
