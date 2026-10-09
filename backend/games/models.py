import secrets
import uuid

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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    join_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    name = models.CharField(max_length=100, default="Track Decode")
    number_of_teams = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2)],
    )
    rounds_per_team = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        default=1,
    )
    default_playback_start_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.LOBBY_OPEN,
    )
    spotify_device_id = models.CharField(max_length=255, blank=True)
    spotify_device_name = models.CharField(max_length=100, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    registration_open = models.BooleanField(default=True)
    current_round = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
