# backend/games/constants.py

from typing import Final

STRING_ERROR_RESPONSES: dict[str, str] = {
    "spotify_not_connected_error_message": "Spotify is not connected.",
    "spotify_could_not_be_reached": "Spotify could not be reached.",
    "invalid_player_session": "Invalid player session.",
    "game_not_in_progress": "The game is not in progress."
}