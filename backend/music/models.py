import uuid

from django.db import models


class Genre(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20, default="#6366F1")
    spotify_playlist_id = models.CharField(max_length=100, blank=True)
    is_enabled = models.BooleanField(default=True)
    exclude_explicit = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "games_genre"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Track(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    spotify_track_id = models.CharField(max_length=100, unique=True)
    spotify_uri = models.CharField(max_length=150, unique=True)
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=300)
    album = models.CharField(max_length=200, blank=True)
    artwork_url = models.URLField(blank=True)
    duration_ms = models.PositiveIntegerField()
    is_explicit = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "games_track"
        ordering = ("title", "artist")

    def __str__(self):
        return f"{self.title} — {self.artist}"
