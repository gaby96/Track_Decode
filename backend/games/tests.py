import asyncio
import hashlib
import time
import uuid
from unittest.mock import Mock, patch

import httpx
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import GameAdmin
from .models import (
    JOIN_CODE_LENGTH,
    Game,
    GameTurn,
    Genre,
    Player,
    ScoreEvent,
    Team,
    Track,
)
from .routing import websocket_urlpatterns
from .views import PLAYBACK_CLIP_DURATION_SECONDS


@override_settings(
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
)
class GameRealtimeTests(TransactionTestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.host = user_model.objects.create_user(
            username="host",
            password="test-pass-123",
        )
        self.game = Game.objects.create(
            host=self.host,
            name="Music Quiz",
            number_of_teams=2,
            status=Game.Status.IN_PROGRESS,
            current_round=1,
            registration_open=False,
        )
        self.team = Team.objects.create(
            game=self.game,
            name="Team 1",
            color="#EF4444",
            position=1,
        )
        self.track = Track.objects.create(
            spotify_track_id="spotify-track-1",
            spotify_uri="spotify:track:spotify-track-1",
            title="Hidden Song",
            artist="Secret Artist",
            album="Quiz Album",
            artwork_url="https://example.com/art.jpg",
            duration_ms=180000,
        )
        self.turn = GameTurn.objects.create(
            game=self.game,
            team=self.team,
            round_number=1,
            turn_position=1,
            status=GameTurn.Status.AWAITING_ANSWER,
            track=self.track,
            started_at=timezone.now(),
        )

    async def _connect(self) -> WebsocketCommunicator:
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/games/{self.game.join_token}/",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        ready_message = await communicator.receive_json_from()
        self.assertEqual(
            ready_message,
            {
                "type": "connection.ready",
                "join_token": str(self.game.join_token),
            },
        )
        return communicator

    def test_websocket_receives_broadcast_game_event(self) -> None:
        async def run_test() -> None:
            communicator = await self._connect()

            try:
                channel_layer = get_channel_layer()
                assert channel_layer is not None

                await channel_layer.group_send(
                    f"game_{self.game.join_token}",
                    {
                        "type": "game.event",
                        "payload": {
                            "type": "round.started",
                            "data": {
                                "game_id": str(self.game.pk),
                                "turn_id": str(self.turn.pk),
                            },
                        },
                    },
                )

                message = await communicator.receive_json_from()

                self.assertEqual(
                    message,
                    {
                        "type": "round.started",
                        "data": {
                            "game_id": str(self.game.pk),
                            "turn_id": str(self.turn.pk),
                        },
                    },
                )
            finally:
                await communicator.disconnect()

        asyncio.run(run_test())

    def test_websocket_track_ready_event_hides_song_and_artist_before_reveal(
        self,
    ) -> None:
        async def run_test() -> None:
            genre = await sync_to_async(Genre.objects.create)(
                name="Synthwave",
                color="#00D1B2",
                spotify_playlist_id="playlist-ws-1",
                exclude_explicit=True,
            )
            player = await sync_to_async(Player.objects.create)(
                game=self.game,
                team=self.team,
                display_name="Leader",
                session_token_hash="leader-session-hash",
            )
            self.team.leader = player
            await sync_to_async(self.team.save)(update_fields=["leader"])

            self.turn.status = GameTurn.Status.GENRE_SELECTED
            self.turn.track = None
            self.turn.genre = genre
            await sync_to_async(self.turn.save)(
                update_fields=[
                    "status",
                    "track",
                    "genre",
                ]
            )

            communicator = await self._connect()

            try:
                await sync_to_async(self.client.force_login, thread_sensitive=True)(
                    self.host
                )
                def configure_host_session() -> None:
                    session = self.client.session
                    session["spotify_tokens"] = {
                        "access_token": "spotify-access-token",
                        "expires_at": int(time.time()) + 3600,
                    }
                    session.save()

                await sync_to_async(
                    configure_host_session,
                    thread_sensitive=True,
                )()

                playlist_total_response = Mock()
                playlist_total_response.json.return_value = {"total": 1}
                playlist_total_response.raise_for_status.return_value = None

                playlist_items_response = Mock()
                playlist_items_response.json.return_value = {
                    "items": [
                        {
                            "item": {
                                "type": "track",
                                "id": "spotify-track-ws-1",
                                "uri": "spotify:track:spotify-track-ws-1",
                                "duration_ms": 150000,
                                "name": "Private Song",
                                "explicit": False,
                                "is_playable": True,
                                "artists": [{"name": "Private Artist"}],
                                "album": {
                                    "name": "Private Album",
                                    "images": [
                                        {
                                            "url": (
                                                "https://example.com/private.jpg"
                                            )
                                        }
                                    ],
                                },
                            }
                        }
                    ]
                }
                playlist_items_response.raise_for_status.return_value = None

                with (
                    patch(
                        "games.views.secrets.SystemRandom.choice",
                        side_effect=lambda sequence: sequence[0],
                    ),
                    patch(
                        "games.views.secrets.SystemRandom.randint",
                        side_effect=lambda start, end: start,
                    ),
                    patch(
                        "games.views.httpx.get",
                        side_effect=[
                            playlist_total_response,
                            playlist_items_response,
                        ],
                    ),
                ):
                    response = await sync_to_async(
                        self.client.post,
                        thread_sensitive=True,
                    )(
                        reverse(
                            "games:prepare-random-track",
                            kwargs={
                                "game_id": self.game.pk,
                                "turn_id": self.turn.pk,
                            },
                        )
                    )

                self.assertEqual(response.status_code, 200)

                message = await communicator.receive_json_from()

                self.assertEqual(message["type"], "track.ready")
                self.assertEqual(
                    message["data"]["turn_status"],
                    GameTurn.Status.TRACK_READY,
                )
                self.assertTrue(message["data"]["track_ready"])
                self.assertNotIn("answer", message["data"])
                self.assertNotIn("title", message["data"])
                self.assertNotIn("artist", message["data"])

                track = await sync_to_async(
                    lambda: Track.objects.get(
                        spotify_track_id="spotify-track-ws-1"
                    )
                )()
                self.assertEqual(track.title, "Private Song")
                self.assertEqual(track.artist, "Private Artist")
            finally:
                await communicator.disconnect()

        asyncio.run(run_test())

    def test_game_state_hides_answer_before_reveal(self) -> None:
        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["current_turn"]["status"],
            GameTurn.Status.AWAITING_ANSWER,
        )
        self.assertTrue(payload["current_turn"]["track_ready"])
        self.assertNotIn("answer", payload["current_turn"])

    def test_game_state_returns_404_for_unknown_join_token(self) -> None:
        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": uuid.uuid4()},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_public_game_detail_can_be_loaded_by_join_code(self) -> None:
        response = self.client.get(
            reverse(
                "games:public-game-detail-by-code",
                kwargs={"join_code": self.game.join_code.lower()},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["join_token"], str(self.game.join_token))
        self.assertEqual(payload["join_code"], self.game.join_code)

    def test_public_game_detail_returns_404_for_unknown_join_code(self) -> None:
        response = self.client.get(
            reverse(
                "games:public-game-detail-by-code",
                kwargs={"join_code": "ZZZZZZ"},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_game_generates_short_join_code(self) -> None:
        self.assertEqual(len(self.game.join_code), JOIN_CODE_LENGTH)
        self.assertTrue(self.game.join_code.isalnum())
        self.assertEqual(self.game.join_code, self.game.join_code.upper())

    def test_game_state_hides_title_and_artist_when_track_is_ready(
        self,
    ) -> None:
        Player.objects.create(
            game=self.game,
            team=self.team,
            display_name="Alice",
            session_token_hash="state-member-alice",
        )
        Player.objects.create(
            game=self.game,
            team=self.team,
            display_name="Bob",
            session_token_hash="state-member-bob",
        )
        self.turn.status = GameTurn.Status.TRACK_READY
        genre = Genre.objects.create(
            name="Rock",
            color="#222222",
            spotify_playlist_id="playlist-rock",
            exclude_explicit=True,
        )
        self.turn.genre = genre
        self.turn.save(update_fields=["status", "genre"])

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["current_turn"]["status"],
            GameTurn.Status.TRACK_READY,
        )
        self.assertTrue(payload["current_turn"]["track_ready"])
        self.assertNotIn("answer", payload["current_turn"])
        self.assertNotIn("title", payload["current_turn"])
        self.assertNotIn("artist", payload["current_turn"])
        self.assertEqual(
            payload["standings"][0]["players"],
            [
                {
                    "id": str(
                        Player.objects.get(
                            game=self.game,
                            display_name="Alice",
                        ).pk
                    ),
                    "display_name": "Alice",
                },
                {
                    "id": str(
                        Player.objects.get(
                            game=self.game,
                            display_name="Bob",
                        ).pk
                    ),
                    "display_name": "Bob",
                },
            ],
        )

    def test_game_state_hides_genre_while_turn_is_active(self) -> None:
        genre = Genre.objects.create(
            name="Rock",
            color="#222222",
            spotify_playlist_id="playlist-rock-active",
            exclude_explicit=True,
        )
        self.turn.status = GameTurn.Status.ACTIVE
        self.turn.genre = genre
        self.turn.save(update_fields=["status", "genre"])

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["current_turn"]["status"],
            GameTurn.Status.ACTIVE,
        )
        self.assertIsNone(payload["current_turn"]["genre"])

    def test_game_state_hides_title_and_artist_while_playing(self) -> None:
        self.turn.status = GameTurn.Status.PLAYING
        self.turn.save(update_fields=["status"])

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["current_turn"]["status"],
            GameTurn.Status.PLAYING,
        )
        self.assertTrue(payload["current_turn"]["track_ready"])
        self.assertNotIn("answer", payload["current_turn"])
        self.assertNotIn("title", payload["current_turn"])
        self.assertNotIn("artist", payload["current_turn"])

    def test_game_state_includes_answer_after_reveal(self) -> None:
        self.turn.status = GameTurn.Status.ANSWER_REVEALED
        self.turn.answer_revealed_at = timezone.now()
        self.turn.save(
            update_fields=[
                "status",
                "answer_revealed_at",
            ]
        )

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["current_turn"]["status"],
            GameTurn.Status.ANSWER_REVEALED,
        )
        self.assertEqual(
            payload["current_turn"]["answer"],
            {
                "title": self.track.title,
                "artist": self.track.artist,
                "album": self.track.album,
                "artwork_url": self.track.artwork_url,
            },
        )

    def test_game_state_includes_answer_after_completion(self) -> None:
        self.turn.status = GameTurn.Status.COMPLETED
        self.turn.completed_at = timezone.now()
        self.turn.save(
            update_fields=[
                "status",
                "completed_at",
            ]
        )

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["current_turn"]["status"],
            GameTurn.Status.COMPLETED,
        )
        self.assertEqual(
            payload["current_turn"]["answer"],
            {
                "title": self.track.title,
                "artist": self.track.artist,
                "album": self.track.album,
                "artwork_url": self.track.artwork_url,
            },
        )

    def test_game_state_orders_standings_by_score(self) -> None:
        other_team = Team.objects.create(
            game=self.game,
            name="Team 2",
            color="#3B82F6",
            position=2,
        )
        other_turn = GameTurn.objects.create(
            game=self.game,
            team=other_team,
            round_number=1,
            turn_position=2,
            status=GameTurn.Status.WAITING,
        )
        ScoreEvent.objects.create(
            game=self.game,
            turn=self.turn,
            team=self.team,
            song_title_correct=True,
            artist_correct=True,
            points=3,
            awarded_by=self.host,
        )
        ScoreEvent.objects.create(
            game=self.game,
            turn=other_turn,
            team=other_team,
            song_title_correct=True,
            artist_correct=False,
            points=1,
            awarded_by=self.host,
        )

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        standings = response.json()["standings"]

        self.assertEqual(
            [entry["name"] for entry in standings],
            [self.team.name, other_team.name],
        )
        self.assertEqual(
            [entry["rank"] for entry in standings],
            [1, 2],
        )

    def test_game_state_reports_team_scores_and_tied_rankings(self) -> None:
        second_team = Team.objects.create(
            game=self.game,
            name="Team 2",
            color="#3B82F6",
            position=2,
        )
        third_team = Team.objects.create(
            game=self.game,
            name="Team 3",
            color="#22C55E",
            position=3,
        )
        second_turn = GameTurn.objects.create(
            game=self.game,
            team=second_team,
            round_number=1,
            turn_position=2,
            status=GameTurn.Status.WAITING,
        )
        third_turn = GameTurn.objects.create(
            game=self.game,
            team=third_team,
            round_number=1,
            turn_position=3,
            status=GameTurn.Status.WAITING,
        )

        ScoreEvent.objects.create(
            game=self.game,
            turn=self.turn,
            team=self.team,
            song_title_correct=True,
            artist_correct=True,
            points=3,
            awarded_by=self.host,
        )
        ScoreEvent.objects.create(
            game=self.game,
            turn=second_turn,
            team=second_team,
            song_title_correct=True,
            artist_correct=True,
            points=3,
            awarded_by=self.host,
        )
        ScoreEvent.objects.create(
            game=self.game,
            turn=third_turn,
            team=third_team,
            song_title_correct=True,
            artist_correct=False,
            points=1,
            awarded_by=self.host,
        )

        response = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": self.game.join_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        standings = response.json()["standings"]

        self.assertEqual(
            [
                (entry["name"], entry["total_points"], entry["rank"])
                for entry in standings
            ],
            [
                (self.team.name, 3, 1),
                (second_team.name, 3, 1),
                (third_team.name, 1, 3),
            ],
        )

    def test_player_session_detail_returns_current_team_assignment(self) -> None:
        session_token = "player-session-token"
        player = Player.objects.create(
            game=self.game,
            display_name="Alice",
            team=self.team,
            session_token_hash=(
                "c0cc75e8052f5c7233ef9ee1b9c2167ebb81a9308b1794dfec54c98d9d899ccf"
            ),
        )

        response = self.client.post(
            reverse(
                "games:player-session-detail",
                kwargs={"join_token": self.game.join_token},
            ),
            data={"session_token": session_token},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["player"]["id"],
            str(player.pk),
        )
        self.assertEqual(
            response.json()["player"]["team"],
            self.team.pk,
        )
        self.assertEqual(
            response.json()["player"]["team_name"],
            self.team.name,
        )

    def test_prepare_track_uses_spotify_tokens_from_other_active_host_session(
        self,
    ) -> None:
        self.client.force_login(self.host)

        genre = Genre.objects.create(
            name="Rock",
            color="#111111",
            spotify_playlist_id="playlist-rock-1",
            exclude_explicit=True,
        )
        self.turn.status = GameTurn.Status.GENRE_SELECTED
        self.turn.genre = genre
        self.turn.track = None
        self.turn.save(
            update_fields=[
                "status",
                "genre",
                "track",
            ]
        )

        fallback_session = SessionStore()
        fallback_session["_auth_user_id"] = str(self.host.pk)
        fallback_session["_auth_user_backend"] = (
            "django.contrib.auth.backends.ModelBackend"
        )
        fallback_session["_auth_user_hash"] = self.host.get_session_auth_hash()
        fallback_session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        fallback_session.save()

        self.assertNotIn("spotify_tokens", self.client.session)

        playlist_total_response = Mock()
        playlist_total_response.json.return_value = {"total": 1}
        playlist_total_response.raise_for_status.return_value = None

        playlist_items_response = Mock()
        playlist_items_response.json.return_value = {
            "items": [
                {
                    "item": {
                        "type": "track",
                        "id": "spotify-track-fallback-1",
                        "uri": "spotify:track:spotify-track-fallback-1",
                        "duration_ms": 150000,
                        "name": "Fallback Song",
                        "explicit": False,
                        "is_playable": True,
                        "artists": [{"name": "Fallback Artist"}],
                        "album": {
                            "name": "Fallback Album",
                            "images": [
                                {"url": "https://example.com/fallback.jpg"}
                            ],
                        },
                    }
                }
            ]
        }
        playlist_items_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.secrets.SystemRandom.choice",
                side_effect=lambda sequence: sequence[0],
            ),
            patch(
                "games.views.secrets.SystemRandom.randint",
                side_effect=lambda start, end: start,
            ),
            patch(
                "games.views.httpx.get",
                side_effect=[
                    playlist_total_response,
                    playlist_items_response,
                ],
            ),
        ):
            response = self.client.post(
                reverse(
                    "games:prepare-random-track",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["track"]["title"],
            "Fallback Song",
        )
        self.assertIn("spotify_tokens", self.client.session)

    def test_open_voting_auto_assigns_single_player_team_leaders(self) -> None:
        flow_game = Game.objects.create(
            host=self.host,
            name="Auto Leader Game",
            number_of_teams=2,
            status=Game.Status.LOBBY_CLOSED,
            current_round=0,
            registration_open=False,
        )
        alice = Player.objects.create(
            game=flow_game,
            display_name="Alice",
            session_token_hash="alice-session-hash",
        )
        bob = Player.objects.create(
            game=flow_game,
            display_name="Bob",
            session_token_hash="bob-session-hash",
        )

        with patch(
            "games.views.random.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            assign_teams = self.client.post(
                reverse(
                    "games:assign-teams",
                    kwargs={"game_id": flow_game.pk},
                )
            )

        self.assertEqual(assign_teams.status_code, 403)

        self.client.force_login(self.host)

        with patch(
            "games.views.random.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            assign_teams = self.client.post(
                reverse(
                    "games:assign-teams",
                    kwargs={"game_id": flow_game.pk},
                )
            )

        self.assertEqual(assign_teams.status_code, 200)

        open_voting = self.client.post(
            reverse(
                "games:open-voting",
                kwargs={"game_id": flow_game.pk},
            )
        )

        self.assertEqual(open_voting.status_code, 200)
        self.assertEqual(
            open_voting.json()["game"]["status"],
            Game.Status.VOTING_CLOSED,
        )

        alice.refresh_from_db()
        bob.refresh_from_db()

        self.assertEqual(alice.team.leader_id, alice.pk)
        self.assertEqual(bob.team.leader_id, bob.pk)

    def test_assign_teams_auto_assigns_single_player_team_leaders(self) -> None:
        flow_game = Game.objects.create(
            host=self.host,
            name="Assign Teams Auto Leader Game",
            number_of_teams=2,
            status=Game.Status.LOBBY_CLOSED,
            current_round=0,
            registration_open=False,
        )
        alice = Player.objects.create(
            game=flow_game,
            display_name="Alice",
            session_token_hash="assign-auto-leader-alice",
        )
        bob = Player.objects.create(
            game=flow_game,
            display_name="Bob",
            session_token_hash="assign-auto-leader-bob",
        )

        self.client.force_login(self.host)

        with patch(
            "games.views.random.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            assign_teams = self.client.post(
                reverse(
                    "games:assign-teams",
                    kwargs={"game_id": flow_game.pk},
                )
            )

        self.assertEqual(assign_teams.status_code, 200)

        alice.refresh_from_db()
        bob.refresh_from_db()

        self.assertEqual(alice.team.leader_id, alice.pk)
        self.assertEqual(bob.team.leader_id, bob.pk)

    def test_start_game_auto_assigns_missing_single_player_team_leaders(self) -> None:
        flow_game = Game.objects.create(
            host=self.host,
            name="Start Game Auto Leader Recovery",
            number_of_teams=2,
            status=Game.Status.VOTING_CLOSED,
            current_round=0,
            registration_open=False,
        )
        team_one = Team.objects.create(
            game=flow_game,
            name="Team 1",
            color="#EF4444",
            position=1,
        )
        team_two = Team.objects.create(
            game=flow_game,
            name="Team 2",
            color="#3B82F6",
            position=2,
        )
        alice = Player.objects.create(
            game=flow_game,
            team=team_one,
            display_name="Alice",
            session_token_hash="start-auto-leader-alice",
        )
        bob = Player.objects.create(
            game=flow_game,
            team=team_two,
            display_name="Bob",
            session_token_hash="start-auto-leader-bob",
        )

        self.client.force_login(self.host)

        with patch(
            "games.views.secrets.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            start_game = self.client.post(
                reverse(
                    "games:start-game",
                    kwargs={"game_id": flow_game.pk},
                )
            )

        self.assertEqual(start_game.status_code, 200)

        team_one.refresh_from_db()
        team_two.refresh_from_db()

        self.assertEqual(team_one.leader_id, alice.pk)
        self.assertEqual(team_two.leader_id, bob.pk)

    def test_single_player_team_does_not_vote_when_voting_open(self) -> None:
        alice_token = "solo-mixed-alice-token"
        bob_token = "solo-mixed-bob-token"
        cara_token = "solo-mixed-cara-token"

        flow_game = Game.objects.create(
            host=self.host,
            name="Mixed Voting Game",
            number_of_teams=2,
            status=Game.Status.LOBBY_CLOSED,
            current_round=0,
            registration_open=False,
        )
        alice = Player.objects.create(
            game=flow_game,
            display_name="Alice",
            session_token_hash=hashlib.sha256(
                alice_token.encode("utf-8")
            ).hexdigest(),
        )
        bob = Player.objects.create(
            game=flow_game,
            display_name="Bob",
            session_token_hash=hashlib.sha256(
                bob_token.encode("utf-8")
            ).hexdigest(),
        )
        cara = Player.objects.create(
            game=flow_game,
            display_name="Cara",
            session_token_hash=hashlib.sha256(
                cara_token.encode("utf-8")
            ).hexdigest(),
        )

        self.client.force_login(self.host)

        with patch(
            "games.views.random.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            assign_teams = self.client.post(
                reverse(
                    "games:assign-teams",
                    kwargs={"game_id": flow_game.pk},
                )
            )

        self.assertEqual(assign_teams.status_code, 200)

        open_voting = self.client.post(
            reverse(
                "games:open-voting",
                kwargs={"game_id": flow_game.pk},
            )
        )

        self.assertEqual(open_voting.status_code, 200)
        self.assertEqual(
            open_voting.json()["game"]["status"],
            Game.Status.VOTING_OPEN,
        )

        alice.refresh_from_db()
        bob.refresh_from_db()
        cara.refresh_from_db()

        self.assertEqual(alice.team_id, cara.team_id)
        self.assertNotEqual(alice.team_id, bob.team_id)
        self.assertEqual(bob.team.leader_id, bob.pk)

        solo_candidates = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": bob_token},
            content_type="application/json",
        )

        self.assertEqual(solo_candidates.status_code, 200)
        self.assertFalse(solo_candidates.json()["requires_vote"])
        self.assertEqual(solo_candidates.json()["team_player_count"], 1)

        team_candidates = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": alice_token},
            content_type="application/json",
        )

        self.assertEqual(team_candidates.status_code, 200)
        self.assertTrue(team_candidates.json()["requires_vote"])
        self.assertEqual(team_candidates.json()["team_player_count"], 2)

        solo_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(bob.pk)},
            content_type="application/json",
            headers={"X-Player-Token": bob_token},
        )

        self.assertEqual(solo_vote.status_code, 409)
        self.assertEqual(
            solo_vote.json()["detail"],
            "Leader voting is not required when your team has only one player.",
        )

    def test_player_cannot_change_leader_vote_after_submitting(self) -> None:
        alice_token = "locked-vote-alice-token"
        bob_token = "locked-vote-bob-token"

        flow_game = Game.objects.create(
            host=self.host,
            name="Locked Vote Game",
            number_of_teams=2,
            status=Game.Status.VOTING_OPEN,
            current_round=0,
            registration_open=False,
        )
        team_one = Team.objects.create(
            game=flow_game,
            name="Team 1",
            color="#EF4444",
            position=1,
        )
        Team.objects.create(
            game=flow_game,
            name="Team 2",
            color="#3B82F6",
            position=2,
        )
        alice = Player.objects.create(
            game=flow_game,
            team=team_one,
            display_name="Alice",
            session_token_hash=hashlib.sha256(
                alice_token.encode("utf-8")
            ).hexdigest(),
        )
        bob = Player.objects.create(
            game=flow_game,
            team=team_one,
            display_name="Bob",
            session_token_hash=hashlib.sha256(
                bob_token.encode("utf-8")
            ).hexdigest(),
        )

        first_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(alice.pk)},
            content_type="application/json",
            headers={"X-Player-Token": alice_token},
        )

        self.assertEqual(first_vote.status_code, 201)

        candidates_after_vote = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": alice_token},
            content_type="application/json",
        )

        self.assertEqual(candidates_after_vote.status_code, 200)
        self.assertTrue(candidates_after_vote.json()["has_voted"])

        second_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(bob.pk)},
            content_type="application/json",
            headers={"X-Player-Token": alice_token},
        )

        self.assertEqual(second_vote.status_code, 409)
        self.assertEqual(
            second_vote.json()["detail"],
            "You have already submitted your leader vote.",
        )

    def test_close_voting_auto_assigns_single_player_team_without_existing_leader(
        self,
    ) -> None:
        flow_game = Game.objects.create(
            host=self.host,
            name="Close Voting Solo Leader Recovery",
            number_of_teams=2,
            status=Game.Status.VOTING_OPEN,
            current_round=0,
            registration_open=False,
        )
        team_one = Team.objects.create(
            game=flow_game,
            name="Team 1",
            color="#EF4444",
            position=1,
        )
        team_two = Team.objects.create(
            game=flow_game,
            name="Team 2",
            color="#3B82F6",
            position=2,
        )
        alice = Player.objects.create(
            game=flow_game,
            team=team_one,
            display_name="Alice",
            session_token_hash="close-voting-alice",
        )
        bob = Player.objects.create(
            game=flow_game,
            team=team_two,
            display_name="Bob",
            session_token_hash="close-voting-bob",
        )

        self.client.force_login(self.host)

        close_voting = self.client.post(
            reverse(
                "games:close-voting",
                kwargs={"game_id": flow_game.pk},
            )
        )

        self.assertEqual(close_voting.status_code, 200)
        self.assertEqual(
            close_voting.json()["game"]["status"],
            Game.Status.VOTING_CLOSED,
        )

        team_one.refresh_from_db()
        team_two.refresh_from_db()

        self.assertEqual(team_one.leader_id, alice.pk)
        self.assertEqual(team_two.leader_id, bob.pk)

    def test_complete_game_flow_integration(self) -> None:
        flow_game = Game.objects.create(
            host=self.host,
            name="Flow Game",
            number_of_teams=2,
            status=Game.Status.LOBBY_OPEN,
            current_round=0,
            registration_open=True,
            spotify_device_id="device-123",
            spotify_device_name="House Speakers",
        )

        genre = Genre.objects.create(
            name="Pop",
            color="#FF3366",
            spotify_playlist_id="playlist-123",
            exclude_explicit=True,
        )

        join_url = reverse(
            "games:player-join",
            kwargs={"join_token": flow_game.join_token},
        )
        alice_join = self.client.post(
            join_url,
            data={"display_name": "Alice"},
            content_type="application/json",
        )
        bob_join = self.client.post(
            join_url,
            data={"display_name": "Bob"},
            content_type="application/json",
        )
        cara_join = self.client.post(
            join_url,
            data={"display_name": "Cara"},
            content_type="application/json",
        )
        dan_join = self.client.post(
            join_url,
            data={"display_name": "Dan"},
            content_type="application/json",
        )

        self.assertEqual(alice_join.status_code, 201)
        self.assertEqual(bob_join.status_code, 201)
        self.assertEqual(cara_join.status_code, 201)
        self.assertEqual(dan_join.status_code, 201)

        alice_token = alice_join.json()["session_token"]
        bob_token = bob_join.json()["session_token"]
        cara_token = cara_join.json()["session_token"]
        dan_token = dan_join.json()["session_token"]

        self.client.force_login(self.host)
        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        close_registration = self.client.post(
            reverse(
                "games:close-registration",
                kwargs={"game_id": flow_game.pk},
            )
        )
        self.assertEqual(close_registration.status_code, 200)

        with patch(
            "games.views.random.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            assign_teams = self.client.post(
                reverse(
                    "games:assign-teams",
                    kwargs={"game_id": flow_game.pk},
                )
            )
        self.assertEqual(assign_teams.status_code, 200)

        alice = Player.objects.get(
            game=flow_game,
            display_name="Alice",
        )
        bob = Player.objects.get(
            game=flow_game,
            display_name="Bob",
        )
        cara = Player.objects.get(
            game=flow_game,
            display_name="Cara",
        )
        dan = Player.objects.get(
            game=flow_game,
            display_name="Dan",
        )
        self.assertIsNotNone(alice.team)
        self.assertIsNotNone(bob.team)
        self.assertEqual(alice.team_id, cara.team_id)
        self.assertEqual(bob.team_id, dan.team_id)
        self.assertNotEqual(alice.team_id, bob.team_id)

        open_voting = self.client.post(
            reverse(
                "games:open-voting",
                kwargs={"game_id": flow_game.pk},
            )
        )
        self.assertEqual(open_voting.status_code, 200)

        alice_candidates = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": alice_token},
            content_type="application/json",
        )
        bob_candidates = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": bob_token},
            content_type="application/json",
        )
        self.assertEqual(alice_candidates.status_code, 200)
        self.assertEqual(bob_candidates.status_code, 200)

        cara_candidates = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": cara_token},
            content_type="application/json",
        )
        dan_candidates = self.client.post(
            reverse(
                "games:team-voting-candidates",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"session_token": dan_token},
            content_type="application/json",
        )
        self.assertEqual(cara_candidates.status_code, 200)
        self.assertEqual(dan_candidates.status_code, 200)

        alice_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(alice.pk)},
            content_type="application/json",
            headers={"X-Player-Token": alice_token},
        )
        bob_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(bob.pk)},
            content_type="application/json",
            headers={"X-Player-Token": bob_token},
        )
        self.assertEqual(alice_vote.status_code, 201)
        self.assertEqual(bob_vote.status_code, 201)

        cara_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(alice.pk)},
            content_type="application/json",
            headers={"X-Player-Token": cara_token},
        )
        dan_vote = self.client.post(
            reverse(
                "games:submit-leader-vote",
                kwargs={"join_token": flow_game.join_token},
            ),
            data={"candidate_id": str(bob.pk)},
            content_type="application/json",
            headers={"X-Player-Token": dan_token},
        )
        self.assertEqual(cara_vote.status_code, 201)
        self.assertEqual(dan_vote.status_code, 201)

        with patch(
            "games.views.secrets.SystemRandom.choice",
            side_effect=lambda sequence: sequence[0],
        ):
            close_voting = self.client.post(
                reverse(
                    "games:close-voting",
                    kwargs={"game_id": flow_game.pk},
                )
            )
        self.assertEqual(close_voting.status_code, 200)

        with patch(
            "games.views.secrets.SystemRandom.shuffle",
            side_effect=lambda sequence: None,
        ):
            start_game = self.client.post(
                reverse(
                    "games:start-game",
                    kwargs={"game_id": flow_game.pk},
                )
            )
        self.assertEqual(start_game.status_code, 200)
        active_turn_id = start_game.json()["active_turn"]["id"]
        active_turn = GameTurn.objects.select_related("team").get(pk=active_turn_id)

        if active_turn.team_id == alice.team_id:
            leader = alice
            leader_token = alice_token
        else:
            leader = bob
            leader_token = bob_token

        self.assertEqual(active_turn.team.leader_id, leader.pk)

        with patch(
            "games.views.secrets.SystemRandom.choice",
            side_effect=lambda sequence: sequence[0],
        ):
            select_genre = self.client.post(
                reverse(
                    "games:select-random-genre",
                    kwargs={
                        "join_token": flow_game.join_token,
                        "turn_id": active_turn.pk,
                    },
                ),
                data={"session_token": leader_token},
                content_type="application/json",
            )
        self.assertEqual(select_genre.status_code, 200)
        self.assertEqual(select_genre.json()["genre"]["id"], str(genre.pk))

        playlist_total_response = Mock()
        playlist_total_response.json.return_value = {"total": 1}
        playlist_total_response.raise_for_status.return_value = None

        playlist_items_response = Mock()
        playlist_items_response.json.return_value = {
            "items": [
                {
                    "item": {
                        "type": "track",
                        "id": "spotify-track-2",
                        "uri": "spotify:track:spotify-track-2",
                        "duration_ms": 120000,
                        "name": "Integration Song",
                        "explicit": False,
                        "is_playable": True,
                        "artists": [{"name": "Integration Artist"}],
                        "album": {
                            "name": "Integration Album",
                            "images": [{"url": "https://example.com/cover.jpg"}],
                        },
                    }
                }
            ]
        }
        playlist_items_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.secrets.SystemRandom.randint",
                side_effect=lambda start, end: start,
            ),
            patch(
                "games.views.secrets.SystemRandom.choice",
                side_effect=lambda sequence: sequence[0],
            ),
            patch(
                "games.views.httpx.get",
                side_effect=[
                    playlist_total_response,
                    playlist_items_response,
                ],
            ),
        ):
            prepare_track = self.client.post(
                reverse(
                    "games:prepare-random-track",
                    kwargs={
                        "game_id": flow_game.pk,
                        "turn_id": active_turn.pk,
                    },
                )
            )
        self.assertEqual(prepare_track.status_code, 200)
        self.assertEqual(
            prepare_track.json()["track"]["title"],
            "Integration Song",
        )

        spotify_put_response = Mock()
        spotify_put_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                return_value=spotify_put_response,
            ),
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            start_playback = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": flow_game.pk,
                        "turn_id": active_turn.pk,
                    },
                )
            )
            self.assertEqual(start_playback.status_code, 200)
            apply_async.assert_called_once()
            self.assertEqual(
                start_playback.json()["clip_duration_seconds"],
                PLAYBACK_CLIP_DURATION_SECONDS,
            )
            self.assertEqual(
                apply_async.call_args.kwargs["countdown"],
                PLAYBACK_CLIP_DURATION_SECONDS,
            )

            stop_playback = self.client.post(
                reverse(
                    "games:stop-track-playback",
                    kwargs={
                        "game_id": flow_game.pk,
                        "turn_id": active_turn.pk,
                    },
                )
            )
            self.assertEqual(stop_playback.status_code, 200)

        hidden_state = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": flow_game.join_token},
            )
        )
        self.assertEqual(hidden_state.status_code, 200)
        self.assertNotIn(
            "answer",
            hidden_state.json()["current_turn"],
        )

        reveal_answer = self.client.post(
            reverse(
                "games:reveal-answer",
                kwargs={
                    "game_id": flow_game.pk,
                    "turn_id": active_turn.pk,
                },
            )
        )
        self.assertEqual(reveal_answer.status_code, 200)
        self.assertEqual(
            reveal_answer.json()["answer"]["title"],
            "Integration Song",
        )

        revealed_state = self.client.get(
            reverse(
                "games:game-state",
                kwargs={"join_token": flow_game.join_token},
            )
        )
        self.assertEqual(revealed_state.status_code, 200)
        self.assertEqual(
            revealed_state.json()["current_turn"]["answer"]["title"],
            "Integration Song",
        )

        award_score = self.client.post(
            reverse(
                "games:award-score",
                kwargs={
                    "game_id": flow_game.pk,
                    "turn_id": active_turn.pk,
                },
            ),
            data={
                "song_title_correct": True,
                "artist_correct": False,
            },
            content_type="application/json",
        )
        self.assertEqual(award_score.status_code, 201)
        self.assertEqual(
            award_score.json()["result"]["points_awarded"],
            1,
        )

        advance_turn = self.client.post(
            reverse(
                "games:advance-turn",
                kwargs={
                    "game_id": flow_game.pk,
                    "turn_id": active_turn.pk,
                },
            )
        )
        self.assertEqual(advance_turn.status_code, 200)
        self.assertTrue(advance_turn.json()["advanced"])
        self.assertEqual(
            advance_turn.json()["active_turn"]["status"],
            GameTurn.Status.ACTIVE,
        )

        next_turn = GameTurn.objects.get(pk=advance_turn.json()["active_turn"]["id"])
        self.assertNotEqual(next_turn.pk, active_turn.pk)
        self.assertEqual(next_turn.turn_position, 2)
        self.assertEqual(
            ScoreEvent.objects.get(turn=active_turn).points,
            1,
        )

        finish_game = self.client.post(
            reverse(
                "games:finish-game",
                kwargs={"game_id": flow_game.pk},
            )
        )
        self.assertEqual(finish_game.status_code, 200)
        finish_payload = finish_game.json()

        self.assertTrue(finish_payload["finished"])
        self.assertIsNotNone(finish_payload["finished_at"])
        self.assertEqual(
            finish_payload["game"]["status"],
            Game.Status.FINISHED,
        )
        self.assertFalse(finish_payload["game"]["registration_open"])
        self.assertEqual(len(finish_payload["winners"]), 1)
        self.assertEqual(
            finish_payload["winners"][0]["team_id"],
            str(active_turn.team_id),
        )
        self.assertEqual(
            [
                (
                    entry["team_id"],
                    entry["score"],
                    entry["rank"],
                )
                for entry in finish_payload["standings"]
            ],
            [
                (str(active_turn.team_id), 1, 1),
                (str(next_turn.team_id), 0, 2),
            ],
        )

        flow_game.refresh_from_db()
        self.assertEqual(flow_game.status, Game.Status.FINISHED)
        self.assertIsNotNone(flow_game.finished_at)

    def test_restart_game_resets_room_to_open_lobby_with_players_preserved(
        self,
    ) -> None:
        self.client.force_login(self.host)

        player_one = Player.objects.create(
            game=self.game,
            team=self.team,
            display_name="Gabriel",
            session_token_hash="restart-player-1",
        )
        player_two = Player.objects.create(
            game=self.game,
            team=self.team,
            display_name="Patricia",
            session_token_hash="restart-player-2",
        )
        self.team.leader = player_one
        self.team.save(update_fields=["leader"])

        second_team = Team.objects.create(
            game=self.game,
            name="Team 2",
            color="#3B82F6",
            position=2,
            leader=player_two,
        )
        second_turn = GameTurn.objects.create(
            game=self.game,
            team=second_team,
            round_number=1,
            turn_position=2,
            status=GameTurn.Status.COMPLETED,
            track=self.track,
        )
        ScoreEvent.objects.create(
            game=self.game,
            turn=self.turn,
            team=self.team,
            song_title_correct=True,
            artist_correct=True,
            points=3,
            awarded_by=self.host,
        )
        ScoreEvent.objects.create(
            game=self.game,
            turn=second_turn,
            team=second_team,
            song_title_correct=False,
            artist_correct=False,
            points=0,
            awarded_by=self.host,
        )

        self.game.status = Game.Status.FINISHED
        self.game.finished_at = timezone.now()
        self.game.registration_open = False
        self.game.current_round = 1
        self.game.save(
            update_fields=[
                "status",
                "finished_at",
                "registration_open",
                "current_round",
            ]
        )

        response = self.client.post(
            reverse(
                "games:restart-game",
                kwargs={"game_id": self.game.pk},
            )
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["restarted"])
        self.assertEqual(
            payload["game"]["status"],
            Game.Status.LOBBY_OPEN,
        )
        self.assertTrue(payload["game"]["registration_open"])
        self.assertEqual(payload["game"]["current_round"], 0)
        self.assertIsNone(payload["game"]["finished_at"])
        self.assertEqual(payload["player_count"], 2)

        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.LOBBY_OPEN)
        self.assertTrue(self.game.registration_open)
        self.assertEqual(self.game.current_round, 0)
        self.assertIsNone(self.game.finished_at)

        self.assertFalse(Team.objects.filter(game=self.game).exists())
        self.assertFalse(GameTurn.objects.filter(game=self.game).exists())
        self.assertFalse(ScoreEvent.objects.filter(game=self.game).exists())
        self.assertEqual(
            Player.objects.filter(game=self.game, team__isnull=True).count(),
            2,
        )

    def test_start_next_round_rejects_when_round_limit_reached(self) -> None:
        self.client.force_login(self.host)

        self.game.rounds_per_team = 1
        self.game.current_round = 1
        self.game.status = Game.Status.IN_PROGRESS
        self.game.save(
            update_fields=[
                "rounds_per_team",
                "current_round",
                "status",
            ]
        )

        self.turn.status = GameTurn.Status.COMPLETED
        self.turn.save(update_fields=["status"])

        second_team = Team.objects.create(
            game=self.game,
            name="Team 2",
            color="#3B82F6",
            position=2,
        )
        GameTurn.objects.create(
            game=self.game,
            team=second_team,
            round_number=1,
            turn_position=2,
            status=GameTurn.Status.COMPLETED,
            track=self.track,
        )

        response = self.client.post(
            reverse(
                "games:start-next-round",
                kwargs={"game_id": self.game.pk},
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["round_limit_reached"])
        self.assertEqual(response.json()["current_round"], 1)
        self.assertEqual(response.json()["rounds_per_team"], 1)
        self.assertEqual(
            response.json()["detail"],
            "The configured round limit has been reached. Finish the game to show the final results.",
        )

    def test_host_can_update_rounds_per_team_for_existing_game(self) -> None:
        self.client.force_login(self.host)

        response = self.client.patch(
            reverse(
                "games:update-game-rounds",
                kwargs={"game_id": self.game.pk},
            ),
            data={
                "rounds_per_team": 3,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["rounds_per_team"], 3)

        self.game.refresh_from_db()
        self.assertEqual(self.game.rounds_per_team, 3)

    def test_host_cannot_reduce_live_rounds_below_current_round(self) -> None:
        self.client.force_login(self.host)

        self.game.current_round = 2
        self.game.rounds_per_team = 3
        self.game.status = Game.Status.IN_PROGRESS
        self.game.save(
            update_fields=[
                "current_round",
                "rounds_per_team",
                "status",
            ]
        )

        response = self.client.patch(
            reverse(
                "games:update-game-rounds",
                kwargs={"game_id": self.game.pk},
            ),
            data={
                "rounds_per_team": 1,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "Rounds per team cannot be set below the current round while the game is in progress.",
        )

        self.game.refresh_from_db()
        self.assertEqual(self.game.rounds_per_team, 3)

    def test_game_admin_exposes_default_playback_start_ms(self) -> None:
        request = RequestFactory().get("/admin/games/game/")
        request.user = self.host

        model_admin = GameAdmin(Game, admin.site)
        form = model_admin.get_form(request, obj=self.game)

        self.assertIn("default_playback_start_ms", form.base_fields)
        self.assertNotIn(
            "default_playback_start_ms",
            model_admin.readonly_fields,
        )

    def test_start_playback_uses_game_default_playback_start_ms(self) -> None:
        self.client.force_login(self.host)

        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        genre = Genre.objects.create(
            name="Offset Rock",
            color="#222222",
            spotify_playlist_id="playlist-offset-rock",
            exclude_explicit=True,
        )

        self.game.spotify_device_id = "device-123"
        self.game.spotify_device_name = "House Speakers"
        self.game.default_playback_start_ms = 12000
        self.game.save(
            update_fields=[
                "spotify_device_id",
                "spotify_device_name",
                "default_playback_start_ms",
            ]
        )

        self.turn.status = GameTurn.Status.TRACK_READY
        self.turn.genre = genre
        self.turn.playback_start_ms = 3000
        self.turn.save(
            update_fields=[
                "status",
                "genre",
                "playback_start_ms",
            ]
        )

        spotify_put_response = Mock()
        spotify_put_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                return_value=spotify_put_response,
            ) as mocked_put,
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            response = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocked_put.call_count, 1)
        self.assertEqual(
            mocked_put.call_args.kwargs["json"]["position_ms"],
            12000,
        )
        apply_async.assert_called_once()

    def test_start_playback_defaults_to_zero_offset(self) -> None:
        self.client.force_login(self.host)

        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        genre = Genre.objects.create(
            name="Zero Offset Rock",
            color="#111111",
            spotify_playlist_id="playlist-zero-offset",
            exclude_explicit=True,
        )

        self.game.spotify_device_id = "device-123"
        self.game.spotify_device_name = "House Speakers"
        self.game.save(
            update_fields=[
                "spotify_device_id",
                "spotify_device_name",
            ]
        )

        self.turn.status = GameTurn.Status.TRACK_READY
        self.turn.genre = genre
        self.turn.save(
            update_fields=[
                "status",
                "genre",
            ]
        )

        spotify_put_response = Mock()
        spotify_put_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                return_value=spotify_put_response,
            ) as mocked_put,
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            response = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mocked_put.call_args.kwargs["json"]["position_ms"],
            0,
        )
        apply_async.assert_called_once()

    def test_start_playback_uses_updated_game_default_for_existing_turn(self) -> None:
        self.client.force_login(self.host)

        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        genre = Genre.objects.create(
            name="Updated Offset Rock",
            color="#333333",
            spotify_playlist_id="playlist-updated-offset",
            exclude_explicit=True,
        )

        self.game.spotify_device_id = "device-123"
        self.game.spotify_device_name = "House Speakers"
        self.game.save(
            update_fields=[
                "spotify_device_id",
                "spotify_device_name",
            ]
        )

        self.turn.status = GameTurn.Status.TRACK_READY
        self.turn.genre = genre
        self.turn.save(
            update_fields=[
                "status",
                "genre",
            ]
        )

        self.game.default_playback_start_ms = 15000
        self.game.save(update_fields=["default_playback_start_ms"])

        spotify_put_response = Mock()
        spotify_put_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                return_value=spotify_put_response,
            ) as mocked_put,
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            response = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mocked_put.call_args.kwargs["json"]["position_ms"],
            15000,
        )
        apply_async.assert_called_once()

    def test_start_playback_recovers_when_device_id_rotates(self) -> None:
        self.client.force_login(self.host)

        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        self.game.spotify_device_id = "stale-device-id"
        self.game.spotify_device_name = "Web Player (Chrome)"
        self.game.save(
            update_fields=[
                "spotify_device_id",
                "spotify_device_name",
            ]
        )

        genre = Genre.objects.create(
            name="Rock",
            color="#222222",
            spotify_playlist_id="playlist-rock",
            exclude_explicit=True,
        )
        self.turn.status = GameTurn.Status.TRACK_READY
        self.turn.genre = genre
        self.turn.save(update_fields=["status", "genre"])

        missing_device_response = Mock()
        missing_device_response.status_code = 404
        missing_device_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "device not found",
            request=Mock(),
            response=missing_device_response,
        )

        devices_response = Mock()
        devices_response.raise_for_status.return_value = None
        devices_response.json.return_value = {
            "devices": [
                {
                    "id": "fresh-device-id",
                    "name": "Web Player (Chrome)",
                    "type": "Computer",
                    "is_active": False,
                    "is_restricted": False,
                }
            ]
        }

        successful_play_response = Mock()
        successful_play_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                side_effect=[
                    missing_device_response,
                    successful_play_response,
                ],
            ) as mocked_put,
            patch(
                "games.views.httpx.get",
                return_value=devices_response,
            ) as mocked_get,
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            response = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["device"]["id"],
            "fresh-device-id",
        )
        self.assertEqual(mocked_put.call_count, 2)
        mocked_get.assert_called_once()
        apply_async.assert_called_once()

        self.game.refresh_from_db()
        self.assertEqual(
            self.game.spotify_device_id,
            "fresh-device-id",
        )

    def test_start_playback_allows_replay_from_awaiting_answer(self) -> None:
        self.client.force_login(self.host)

        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        genre = Genre.objects.create(
            name="Replay Rock",
            color="#111111",
            spotify_playlist_id="playlist-replay",
            exclude_explicit=True,
        )

        self.game.spotify_device_id = "device-123"
        self.game.spotify_device_name = "House Speakers"
        self.game.save(
            update_fields=[
                "spotify_device_id",
                "spotify_device_name",
            ]
        )

        self.turn.status = GameTurn.Status.AWAITING_ANSWER
        self.turn.genre = genre
        self.turn.playback_stopped_at = timezone.now()
        self.turn.save(
            update_fields=[
                "status",
                "genre",
                "playback_stopped_at",
            ]
        )

        spotify_put_response = Mock()
        spotify_put_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                return_value=spotify_put_response,
            ) as mocked_put,
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            response = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["turn"]["status"],
            GameTurn.Status.PLAYING,
        )
        self.assertEqual(
            mocked_put.call_args.kwargs["json"]["position_ms"],
            0,
        )
        apply_async.assert_called_once()

        self.turn.refresh_from_db()
        self.assertEqual(
            self.turn.status,
            GameTurn.Status.PLAYING,
        )

    def test_replay_uses_game_default_playback_start_ms(self) -> None:
        self.client.force_login(self.host)

        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

        genre = Genre.objects.create(
            name="Replay Offset Rock",
            color="#444444",
            spotify_playlist_id="playlist-replay-offset",
            exclude_explicit=True,
        )

        self.game.spotify_device_id = "device-123"
        self.game.spotify_device_name = "House Speakers"
        self.game.default_playback_start_ms = 12000
        self.game.save(
            update_fields=[
                "spotify_device_id",
                "spotify_device_name",
                "default_playback_start_ms",
            ]
        )

        self.turn.status = GameTurn.Status.AWAITING_ANSWER
        self.turn.genre = genre
        self.turn.playback_start_ms = 5000
        self.turn.playback_stopped_at = timezone.now()
        self.turn.save(
            update_fields=[
                "status",
                "genre",
                "playback_start_ms",
                "playback_stopped_at",
            ]
        )

        spotify_put_response = Mock()
        spotify_put_response.raise_for_status.return_value = None

        with (
            patch(
                "games.views.httpx.put",
                return_value=spotify_put_response,
            ) as mocked_put,
            patch("games.views.stop_spotify_playback.apply_async") as apply_async,
        ):
            response = self.client.post(
                reverse(
                    "games:start-track-playback",
                    kwargs={
                        "game_id": self.game.pk,
                        "turn_id": self.turn.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mocked_put.call_args.kwargs["json"]["position_ms"],
            12000,
        )
        apply_async.assert_called_once()
