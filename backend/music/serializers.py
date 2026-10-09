from rest_framework import serializers

from .models import Genre, Track


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name", "color")
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
        return f"https://open.spotify.com/track/{track.spotify_track_id}"
