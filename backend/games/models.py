import uuid
import secrets

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 6


def generate_join_code() -> str:
    while True:
        join_code = "".join(
            secrets.choice(JOIN_CODE_ALPHABET)
            for _ in range(JOIN_CODE_LENGTH)
        )

        if not Game.objects.filter(join_code=join_code).exists():
            return join_code


class Game(models.Model):
    class Status(models.TextChoices):
        LOBBY_OPEN = "LOBBY_OPEN", "Lobby open"
        LOBBY_CLOSED = "LOBBY_CLOSED", "Lobby closed"
        VOTING_OPEN = "VOTING_OPEN", "Voting open"
        READY = "READY", "Ready"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        PAUSED = "PAUSED", "Paused"
        FINISHED = "FINISHED", "Finished"
        TEAMS_ASSIGNED = "TEAMS_ASSIGNED", "Teams assigned"
        VOTING_CLOSED = "VOTING_CLOSED", "Voting closed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    join_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    join_code = models.CharField(
        max_length=JOIN_CODE_LENGTH,
        default=generate_join_code,
        unique=True,
        editable=False,
    )
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hosted_games",
    )
    name = models.CharField(
        max_length=100,
        default="Track Decode",
    )
    number_of_teams = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2)],
    )
    rounds_per_team = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        default=1,
    )
    default_playback_start_ms = models.PositiveIntegerField(
        default=0,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.LOBBY_OPEN,
    )
    spotify_device_id = models.CharField(
        max_length=255,
        blank=True,
    )
    spotify_device_name = models.CharField(
        max_length=100,
        blank=True,
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    registration_open = models.BooleanField(default=True)
    current_round = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Team(models.Model):
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20)
    position = models.PositiveSmallIntegerField()
    leader = models.ForeignKey(
        "Player",
        on_delete=models.SET_NULL,
        related_name="led_teams",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("position",)
        constraints = (
            models.UniqueConstraint(
                fields=["game", "position"],
                name="unique_team_position_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "name"],
                name="unique_team_name_per_game",
            ),
        )

    def __str__(self):
        return f"{self.name} — {self.game.name}"


class Player(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="players",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name="players",
        null=True,
        blank=True,
    )
    display_name = models.CharField(max_length=50)
    session_token_hash = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    is_connected = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("joined_at",)
        constraints = (
            models.UniqueConstraint(
                fields=["game", "display_name"],
                name="unique_player_name_per_game",
            ),
        )

    def __str__(self):
        return f"{self.display_name} — {self.game.name}"


class LeaderVote(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="leader_votes",
    )
    voter = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="leader_votes_cast",
    )
    candidate = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="leader_votes_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("team", "voter"),
                name="one_leader_vote_per_player",
            ),
        )

    def __str__(self):
        return f"{self.voter.display_name} voted in {self.team.name}"


class Genre(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=50,
        unique=True,
    )
    color = models.CharField(
        max_length=20,
        default="#6366F1",
    )
    spotify_playlist_id = models.CharField(
        max_length=100,
        blank=True,
    )
    is_enabled = models.BooleanField(default=True)
    exclude_explicit = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


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

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    genre = models.ForeignKey(
        Genre,
        on_delete=models.PROTECT,
        related_name="turns",
        null=True,
        blank=True,
    )
    playback_start_ms = models.PositiveIntegerField(default=0)
    playback_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    playback_stopped_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    track = models.ForeignKey(
        "Track",
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
    answer_revealed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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


class Track(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    spotify_track_id = models.CharField(
        max_length=100,
        unique=True,
    )
    spotify_uri = models.CharField(
        max_length=150,
        unique=True,
    )
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=300)
    album = models.CharField(
        max_length=200,
        blank=True,
    )
    artwork_url = models.URLField(blank=True)
    duration_ms = models.PositiveIntegerField()
    is_explicit = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("title", "artist")

    def __str__(self):
        return f"{self.title} — {self.artist}"


class ScoreEvent(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="score_events",
    )
    turn = models.OneToOneField(
        GameTurn,
        on_delete=models.CASCADE,
        related_name="score_event",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="score_events",
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
        ordering = ("created_at",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(points__in=(0, 1, 3)),
                name="score_points_must_be_0_1_or_3",
            ),
        )

    def __str__(self):
        return f"{self.team.name}: {self.points} points — {self.game.name}"
