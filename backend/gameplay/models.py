import uuid

from django.conf import settings
from django.db import models


class GameTurn(models.Model):
    class Status(models.TextChoices):
        WAITING = "WAITING", "Waiting"
        ACTIVE = "ACTIVE", "Active"
        GENRE_SELECTED = "GENRE_SELECTED", "Genre selected"
        TRACK_READY = "TRACK_READY", "Track ready"
        PLAYING = "PLAYING", "Playing"
        AWAITING_ANSWER = "AWAITING_ANSWER", "Awaiting answer"
        ANSWER_REVEALED = "ANSWER_REVEALED", "Answer revealed"
        COMPLETED = "COMPLETED", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(
        "games.Game", on_delete=models.CASCADE, related_name="turns"
    )
    team = models.ForeignKey(
        "lobby.Team", on_delete=models.CASCADE, related_name="turns"
    )
    genre = models.ForeignKey(
        "music.Genre",
        on_delete=models.PROTECT,
        related_name="turns",
        null=True,
        blank=True,
    )
    playback_start_ms = models.PositiveIntegerField(default=0)
    playback_started_at = models.DateTimeField(null=True, blank=True)
    playback_stopped_at = models.DateTimeField(null=True, blank=True)
    track = models.ForeignKey(
        "music.Track",
        on_delete=models.PROTECT,
        related_name="turns",
        null=True,
        blank=True,
    )
    round_number = models.PositiveIntegerField()
    turn_position = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING,
    )
    answer_revealed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "games_gameturn"
        ordering = ("round_number", "turn_position")
        constraints = (
            models.UniqueConstraint(
                fields=("game", "round_number", "turn_position"),
                name="unique_turn_position_per_round",
            ),
            models.UniqueConstraint(
                fields=("game", "round_number", "team"),
                name="one_turn_per_team_per_round",
            ),
        )

    def __str__(self):
        return f"{self.game.name} — Round {self.round_number} — {self.team.name}"


class ScoreEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(
        "games.Game", on_delete=models.CASCADE, related_name="score_events"
    )
    turn = models.OneToOneField(
        GameTurn, on_delete=models.CASCADE, related_name="score_event"
    )
    team = models.ForeignKey(
        "lobby.Team", on_delete=models.CASCADE, related_name="score_events"
    )
    song_title_correct = models.BooleanField(default=False)
    artist_correct = models.BooleanField(default=False)
    points = models.PositiveSmallIntegerField()
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="awarded_score_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "games_scoreevent"
        ordering = ("created_at",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(points__in=(0, 1, 3)),
                name="score_points_must_be_0_1_or_3",
            ),
        )

    def __str__(self):
        return f"{self.team.name}: {self.points} points — {self.game.name}"
