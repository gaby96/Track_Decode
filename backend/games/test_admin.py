import time
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Game


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class GameAdminSpotifyTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-pass-123",
        )
        self.game = Game.objects.create(
            host=self.admin_user,
            name="Admin Spotify Game",
            number_of_teams=2,
        )
        self.client.force_login(self.admin_user)

    def _connect_spotify_session(self) -> None:
        session = self.client.session
        session["spotify_tokens"] = {
            "access_token": "spotify-access-token",
            "expires_at": int(time.time()) + 3600,
        }
        session.save()

    def test_game_change_page_links_to_spotify_device_picker(self) -> None:
        response = self.client.get(
            reverse(
                "admin:games_game_change",
                args=(self.game.pk,),
            )
        )

        self.assertContains(response, "Select Spotify device")
        self.assertContains(
            response,
            reverse(
                "admin:games_game_spotify",
                args=(self.game.pk,),
            ),
        )

    def test_connect_stores_admin_return_path(self) -> None:
        picker_url = reverse(
            "admin:games_game_spotify",
            args=(self.game.pk,),
        )
        response = self.client.get(
            reverse(
                "admin:games_game_spotify_connect",
                args=(self.game.pk,),
            )
        )

        self.assertRedirects(
            response,
            reverse("games:spotify-login"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session["spotify_oauth_return_to"],
            picker_url,
        )

    def test_device_picker_saves_selected_device(self) -> None:
        self._connect_spotify_session()
        spotify_devices_response = Mock()
        spotify_devices_response.raise_for_status.return_value = None
        spotify_devices_response.json.return_value = {
            "devices": [
                {
                    "id": "device-123",
                    "name": "Kitchen Speaker",
                    "type": "Speaker",
                    "is_active": True,
                    "is_restricted": False,
                }
            ]
        }
        spotify_transfer_response = Mock()
        spotify_transfer_response.raise_for_status.return_value = None

        with (
            patch(
                "games.admin.httpx.get",
                return_value=spotify_devices_response,
            ),
            patch(
                "games.admin.httpx.put",
                return_value=spotify_transfer_response,
            ) as mocked_put,
        ):
            response = self.client.post(
                reverse(
                    "admin:games_game_spotify",
                    args=(self.game.pk,),
                ),
                data={"device_id": "device-123"},
            )

        self.assertRedirects(
            response,
            reverse(
                "admin:games_game_change",
                args=(self.game.pk,),
            ),
        )
        mocked_put.assert_called_once()
        self.game.refresh_from_db()
        self.assertEqual(self.game.spotify_device_id, "device-123")
        self.assertEqual(self.game.spotify_device_name, "Kitchen Speaker")

    @patch("games.views.httpx.post")
    def test_spotify_callback_returns_to_admin_picker(
        self,
        mocked_post,
    ) -> None:
        picker_url = reverse(
            "admin:games_game_spotify",
            args=(self.game.pk,),
        )
        session = self.client.session
        session["spotify_oauth_state"] = "oauth-state"
        session["spotify_oauth_return_to"] = picker_url
        session.save()

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }
        mocked_post.return_value = token_response

        response = self.client.get(
            reverse("games:spotify-callback"),
            data={"code": "spotify-code", "state": "oauth-state"},
        )

        self.assertRedirects(
            response,
            picker_url,
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session["spotify_tokens"]["access_token"],
            "new-access-token",
        )
