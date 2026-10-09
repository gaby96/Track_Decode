import uuid
from typing import Any, cast

from django.db import models


class Team(models.Model):
    game = models.ForeignKey(
        "games.Game", on_delete=models.CASCADE, related_name="teams"
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20)
    position = models.PositiveSmallIntegerField()
    leader: "Player | None" = cast(
        Any,
        models.ForeignKey(
            "Player",
            on_delete=models.SET_NULL,
            related_name="led_teams",
            null=True,
            blank=True,
        ),
    )
    leader_id: uuid.UUID | None

    class Meta:
        db_table = "games_team"
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(
        "games.Game", on_delete=models.CASCADE, related_name="players"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        related_name="players",
        null=True,
        blank=True,
    )
    team_id: int
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
        db_table = "games_player"
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="leader_votes"
    )
    voter = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="leader_votes_cast"
    )
    candidate = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="leader_votes_received"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "games_leadervote"
        ordering = ("created_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("team", "voter"),
                name="one_leader_vote_per_player",
            ),
        )

    def __str__(self):
        return f"{self.voter.display_name} voted in {self.team.name}"
