"""Compatibility exports for entity-focused API view modules.

New code should import from the focused modules directly. These re-exports keep
existing URL configuration and third-party imports stable.
"""

import random
import secrets

import httpx

from .game_views import (
    CloseRegistrationView,
    FinishGameView,
    GameListCreateView,
    GameStateView,
    PublicGameByCodeDetailView,
    PublicGameDetailView,
    RestartGameView,
    StartGameView,
    StartNextRoundView,
    UpdateGameRoundsView,
)
from gameplay.game_turn_views import (
    PLAYBACK_CLIP_DURATION_SECONDS,
    AdvanceTurnView,
    RevealAnswerView,
    StartTrackPlaybackView,
    StopTrackPlaybackView,
)
from music.genre_views import SelectRandomGenreView
from lobby.leader_vote_views import (
    CloseVotingView,
    OpenVotingView,
    SubmitLeaderVoteView,
    TeamVotingCandidatesView,
)
from lobby.player_views import (
    HostPlayerListView,
    PlayerJoinView,
    PlayerSessionDetailView,
)
from gameplay.score_event_views import AwardScoreView, PublicLeaderboardView
from spotify.views import (
    SelectSpotifyDeviceView,
    SpotifyCallbackView,
    SpotifyDeviceListView,
    SpotifyLoginView,
    SpotifyStatusView,
)
from .system_views import CsrfTokenView, HealthcheckView
from spotify.tasks import stop_spotify_playback
from lobby.team_views import AssignTeamsView
from music.track_views import PrepareRandomTrackView

__all__ = [
    "AdvanceTurnView",
    "AssignTeamsView",
    "AwardScoreView",
    "CloseRegistrationView",
    "CloseVotingView",
    "CsrfTokenView",
    "FinishGameView",
    "GameListCreateView",
    "GameStateView",
    "HealthcheckView",
    "HostPlayerListView",
    "OpenVotingView",
    "PLAYBACK_CLIP_DURATION_SECONDS",
    "PlayerJoinView",
    "PlayerSessionDetailView",
    "PrepareRandomTrackView",
    "PublicGameByCodeDetailView",
    "PublicGameDetailView",
    "PublicLeaderboardView",
    "RestartGameView",
    "RevealAnswerView",
    "SelectRandomGenreView",
    "SelectSpotifyDeviceView",
    "SpotifyCallbackView",
    "SpotifyDeviceListView",
    "SpotifyLoginView",
    "SpotifyStatusView",
    "StartGameView",
    "StartNextRoundView",
    "StartTrackPlaybackView",
    "StopTrackPlaybackView",
    "SubmitLeaderVoteView",
    "TeamVotingCandidatesView",
    "UpdateGameRoundsView",
]
