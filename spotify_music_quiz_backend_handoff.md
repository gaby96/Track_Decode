# Spotify Music Quiz — Backend Handoff

Last updated: 13 August 2026  
Project stage: Local backend MVP, approximately 90% complete  
Intended reader: Developer or LLM continuing implementation

## 1. Product Summary

This is a browser-based, team music quiz game.

The intended game flow is:

1. An authenticated admin creates a game and chooses the number of teams.
2. Players scan a QR code and join using a display name.
3. The admin closes registration.
4. The backend assigns players randomly into balanced teams.
5. Members of each team privately vote for their team leader.
6. The admin closes voting and the backend elects each team's leader. Ties are resolved randomly.
7. The admin starts the game. Only one team is active at a time.
8. The active team's elected leader randomly selects a music genre through the app.
9. The admin prepares a random eligible Spotify track from the selected genre's curated playlist.
10. One central Spotify Premium device plays a 10-second clip.
11. The active team guesses the song title and artist verbally.
12. The admin reveals the answer and awards points.
13. The game advances to the next team, another round, or the final results.

Final scoring rule:

| Result | Points |
| --- | ---: |
| Song title and artist both correct | 3 |
| Only song title correct | 1 |
| Only artist correct | 1 |
| Neither correct | 0 |

Only the active team is allowed to answer. Scoring is controlled by the admin.

## 2. Repository Layout

The user's local project is arranged as follows:

```text
Spotify_Game/
├── compose.yaml
├── backend/
│   ├── .dockerignore
│   ├── .env
│   ├── Dockerfile
│   ├── manage.py
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── config/
│   │   ├── asgi.py
│   │   ├── celery.py
│   │   ├── settings.py
│   │   └── urls.py
│   └── games/
│       ├── admin.py
│       ├── consumers.py
│       ├── models.py
│       ├── realtime.py
│       ├── routing.py
│       ├── serializers.py
│       ├── services/
│       │   └── spotify.py
│       ├── tasks.py
│       ├── test_consumers.py
│       ├── urls.py
│       └── views.py
└── frontend/
    └── not started yet
```

The Compose file is intentionally outside `backend/` because a Nuxt frontend will later live beside the backend.

## 3. Technology Stack

| Component | Technology |
| --- | --- |
| Backend | Django 5.2.17 |
| API | Django REST Framework |
| Python | CPython 3.12.13, Apple Silicon/arm64 |
| Package manager | uv 0.12.3 |
| HTTP client | httpx |
| Background tasks | Celery 5.6.3 |
| Broker | Redis database 0 |
| Real-time transport | Django Channels + Daphne |
| Channel layer | channels-redis, Redis database 1 |
| Containers | OrbStack/Docker Compose |
| Current database | SQLite for local development |
| Planned frontend | Nuxt 3 + TypeScript + Tailwind CSS |
| Music service | Spotify Web API; Premium account required for playback |

The original x86_64 Conda installation of `uv` was replaced with the native arm64 binary at `~/.local/bin/uv`.

## 4. Infrastructure

### Dockerfile

The backend image uses:

```dockerfile
FROM ghcr.io/astral-sh/uv:0.12.3-python3.12-trixie-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --create-home appuser \
    && chown -R appuser:appgroup /app /opt/venv

USER appuser
ENTRYPOINT []

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

The virtual environment is stored at `/opt/venv`. This avoids the host bind mount at `/app` hiding the container's installed packages.

### Compose services

The current Compose configuration contains:

- `redis`: `redis:7-alpine`, persistent `redis_data` volume and health check.
- `web`: Django development server exposed at port 8000.
- `worker`: Celery worker with concurrency 2.
- Both application services mount `./backend:/app`.
- Both depend on a healthy Redis service.

Important environment values:

```text
CELERY_BROKER_URL=redis://redis:6379/0
REDIS_CHANNEL_URL=redis://redis:6379/1
```

Confirmed runtime state:

- Redis starts and reports healthy.
- Django starts through ASGI/Daphne and reports no system-check issues.
- Celery connects to Redis and reports ready.
- Celery discovers `games.tasks.stop_spotify_playback`.
- A browser successfully established a WebSocket connection through Channels and Redis before authentication was added.

Useful commands from the `Spotify_Game` root:

```bash
docker compose up -d --build
docker compose ps
docker compose logs web --tail=100
docker compose logs worker --tail=100
docker compose restart worker
docker compose exec web python manage.py check
docker compose exec web python manage.py test -v 2
```

Celery workers must be restarted after editing task code because they do not use Django's development autoreloader.

## 5. Django Settings

The following configuration has been added:

- `daphne` appears before Django static files in `INSTALLED_APPS`.
- `channels`, `rest_framework`, `corsheaders`, and `games` are installed.
- `ASGI_APPLICATION = "config.asgi.application"`.
- `CHANNEL_LAYERS` uses `channels_redis.core.RedisChannelLayer`.
- The Channels Redis URL defaults to local Redis but is overridden in Compose with `redis://redis:6379/1`.
- Celery uses Redis database 0.
- CORS allows the future frontend on `localhost:3000` and `127.0.0.1:3000`.
- Local allowed hosts include `localhost` and `127.0.0.1`.
- Spotify settings are read from environment variables.

Do not commit `backend/.env`. It contains Spotify credentials.

Spotify redirect URI configured during development:

```text
http://127.0.0.1:8000/api/spotify/callback/
```

## 6. Data Model

The exact source of truth is `games/models.py`. The following models and behavior were implemented.

### Game

- UUID primary key.
- UUID `join_token`, unique and suitable for the QR code.
- Host foreign key to Django user.
- Name and configured number of teams.
- Registration flag and current round.
- Spotify central device ID and name.
- Finished timestamp and normal timestamps.
- Status choices include:
  - `LOBBY_OPEN`
  - `LOBBY_CLOSED`
  - `TEAMS_ASSIGNED`
  - `VOTING_OPEN`
  - `VOTING_CLOSED`
  - `READY`
  - `IN_PROGRESS`
  - `PAUSED`
  - `FINISHED`

### Team

- Belongs to one game.
- Name, color and numeric position.
- Nullable leader foreign key to `Player`.
- Game-scoped uniqueness constraints for name and position.

### Player

- UUID primary key.
- Belongs to one game and optionally a team.
- Display name.
- SHA-256 hash of a private session token; the raw token is returned once when joining and is never stored.
- Connection-related fields were also added.

### LeaderVote

- Explicit UUID primary key.
- Team, voter and candidate.
- One vote per voter per team.

### Genre

- UUID primary key.
- Name and display color.
- Curated Spotify playlist ID.
- `is_enabled` flag.
- `exclude_explicit` flag.

### Track

- UUID primary key.
- Spotify track ID and URI.
- Title, artist, album and artwork URL.
- Duration and explicit-content flag.

### GameTurn

- UUID primary key.
- Game, team, optional genre and optional track.
- Actual field names are `round_number` and `turn_position`.
- Playback offset field is `playback_start_ms`.
- Timestamps for start, playback start/stop, answer reveal and completion.
- Status choices include:
  - `WAITING`
  - `ACTIVE`
  - `GENRE_SELECTED`
  - `TRACK_READY`
  - `PLAYING`
  - `AWAITING_ANSWER`
  - `ANSWER_REVEALED`
  - `COMPLETED`

### ScoreEvent

- UUID primary key.
- Belongs to a game, turn and team.
- One score event per turn.
- Stores `song_title_correct`, `artist_correct`, calculated points and awarding admin.
- Points are constrained to `0`, `1` or `3`.

All game models are registered in Django administration. The user confirmed that `Games` appears in the admin panel.

## 7. API Features Implemented

The following view behavior exists. The exact route spelling must be confirmed from `games/urls.py`; do not infer URLs solely from class names.

### Lobby and teams

- Authenticated host can create and list games.
- Public game details can be fetched using the join token.
- A player can join an open lobby with a display name.
- Joining returns public player data plus a private raw session token.
- Admin can list waiting-room players.
- Admin can close registration.
- Admin can assign players randomly into balanced teams.
- Team sizes differ by no more than one.

### Leader voting

- Admin opens leader voting.
- Players fetch candidates belonging only to their team.
- Players authenticate voting requests with their private session token.
- Each player can create or update one private vote.
- Admin closes voting.
- Leaders are elected per team, with random tie resolution.

### Game flow

- Admin starts the game.
- Turns are created in randomized team order.
- Only one turn is active.
- Only the active team's elected leader can trigger random genre selection.
- Used genres are avoided until all enabled genres have been used.
- Admin prepares a random eligible track from the genre's curated Spotify playlist.
- Previously used tracks are excluded.
- Local, unplayable, too-short and optionally explicit tracks are excluded.
- Admin starts and manually stops playback.
- Celery automatically pauses Spotify after 10 seconds.
- Admin reveals the answer.
- Admin awards 0, 1 or 3 points based on the two correctness booleans.
- The completed turn can advance to the next waiting turn.
- Admin can start another round after all current-round turns are completed.
- Admin can fetch the leaderboard.
- Admin can finish the game, including tied winners and competition ranks such as `1, 1, 3`.

### Reconnection state

A public, answer-safe game-state endpoint was added conceptually at:

```text
GET /api/games/<join_token>/state/
```

It returns:

- Safe game metadata.
- Current round and current/non-waiting turn.
- Team names, colors, leaders, scores and ranks.
- Genre and track-ready state.
- The song title, artist, album and artwork only when the turn is `ANSWER_REVEALED` or `COMPLETED`.

Verify that `GameStateView` and its URL were actually saved in the local repository before relying on this endpoint.

## 8. Spotify Integration

Spotify OAuth and playback support are implemented.

Scopes used include:

- `streaming`
- `user-read-email`
- `user-read-private`
- `user-read-playback-state`
- `user-modify-playback-state`

Implemented behavior:

- Spotify login and callback.
- OAuth tokens stored in the host's Django database-backed session.
- Automatic token refresh in `games/services/spotify.py`.
- Spotify connection-status endpoint.
- Device listing and central-device selection.
- Playlist reading and eligible random-track preparation.
- Playback start at the turn's configured offset.
- Automatic and manual playback pause.

The host needs Spotify Premium and must open Spotify on the chosen central device so the device appears in `/me/player/devices`.

The Celery task receives the Django session key so it can retrieve and refresh the host's Spotify OAuth tokens.

Security rule: track answers may be returned to the authenticated admin, but must never be included in public API or WebSocket payloads before answer reveal.

## 9. Real-Time Architecture

### ASGI routing

`config/asgi.py` uses:

- `ProtocolTypeRouter`
- Django ASGI application for HTTP
- `AllowedHostsOriginValidator`
- `AuthMiddlewareStack`
- `URLRouter` for game WebSockets

WebSocket route:

```text
ws://127.0.0.1:8000/ws/games/<join_token>/
```

Production must use `wss://`.

Type-checking casts were added around `URLRouter` and `path()` because current Django and Channels type stubs disagree even though the runtime code is valid.

### Broadcasting helper

`games/realtime.py` contains `broadcast_game_event(join_token, event_type, data)`.

It calls the Channels group named:

```text
game_<join_token>
```

and sends a Channels handler type of `game.event`, which is received by the consumer's `game_event()` method.

### WebSocket authentication

The consumer was updated so a connection is not added to the game group until authenticated.

- An authenticated Django user who owns the game is recognized as the host through the session cookie.
- A player first receives `authentication.required` and must send:

```json
{
  "type": "authenticate",
  "session_token": "RAW_PLAYER_SESSION_TOKEN"
}
```

- The consumer hashes the token with SHA-256 and verifies that it belongs to a player in that game.
- Invalid tokens receive `authentication.failed` and close with code `4003`.
- Unknown games close with code `4004`.
- Player tokens are deliberately not placed in the WebSocket URL because URLs can appear in logs.

The authentication code was written but should be verified by running the automated tests and a manual browser test.

### Real-time events added

| Event | Trigger | Public content |
| --- | --- | --- |
| `player.joined` | Player joins lobby | Player public identity and count |
| `registration.closed` | Admin closes lobby | Game status |
| `teams.assigned` | Balanced assignment finishes | Teams and public player membership |
| `voting.opened` | Admin opens voting | Game status |
| `voting.progress` | Vote submitted or updated | Counts only; no voter or candidate |
| `voting.closed` | Admin closes voting | Elected leaders |
| `game.started` | Game and first turn start | Active team and turn |
| `genre.selected` | Active leader selects genre | Genre and active team |
| `track.ready` | Admin prepares track | Boolean readiness only; no answer |
| `playback.started` | Spotify starts | Start/end timestamps and 10-second duration |
| `playback.stopped` | Celery or admin pauses Spotify | Stop time and reason |
| `answer.revealed` | Admin reveals answer | Title, artist, album and artwork |
| `score.awarded` | Admin records result | Correctness, points and new team total |
| `turn.advanced` | Next team becomes active | New active turn/team |
| `round.completed` | Final turn of round ends | Completed round number |
| `round.started` | Admin creates next round | New active turn/team |
| `game.finished` | Admin ends game | Winners and final standings |

Most view callbacks use `transaction.on_commit(...)` so clients are notified only after successful database commits. Non-critical broadcast callbacks use `robust=True` so a Redis/WebSocket problem does not invalidate completed game actions.

## 10. Background Playback Task

`games.tasks.stop_spotify_playback` performs the following:

1. Loads the turn with game, team and genre.
2. Exits if the turn is absent or no longer `PLAYING`.
3. Loads the host's database-backed Django session using the passed session key.
4. Obtains or refreshes the Spotify access token.
5. Calls Spotify's pause endpoint for the selected device.
6. Atomically changes the turn from `PLAYING` to `AWAITING_ANSWER`.
7. Broadcasts `playback.stopped` with reason `clip_complete`.

Manual stopping uses reason `admin_manual`. The later Celery task safely exits because the turn is no longer `PLAYING`.

## 11. Tests Written

`games/test_consumers.py` was written with four asynchronous Channels tests using `WebsocketCommunicator` and the in-memory channel layer:

1. A valid player token authenticates successfully.
2. An invalid player token is rejected.
3. An authenticated player receives a game-group event.
4. An unknown game is rejected with close code `4004`.

The tests use `TransactionTestCase` so asynchronous ORM access can see committed setup data.

Run them with:

```bash
docker compose exec web python manage.py test games.test_consumers -v 2
```

At handoff time, the user stated that the tests had been written, but no successful test-run output was provided in the conversation. Treat execution as pending until confirmed.

## 12. Confirmed Development Data

A development game was created earlier with:

```text
game_id: 2ec3e17b-e9e5-426e-a6c8-3fb793c3c065
join_token: 606b6a1d-a27b-4bc3-9f65-4a5fd918e0e4
name: Test Music Quiz
host: gaby96
number_of_teams: 4
```

This record may since have changed or been removed. Query the current database rather than assuming it still exists. Never place raw player session tokens or Spotify secrets in documentation.

## 13. Pylance and Ruff Notes

Several warnings encountered were caused by incomplete typing information for Django's dynamically generated attributes and Channels/Django stub incompatibilities.

Patterns used to resolve them include:

- Cast `request.data` or serializer `validated_data` before indexing or calling `.get()`.
- Use `getattr(model, "field_name")` for dynamic Django fields when Pylance cannot see them.
- Use `getattr(player, "team_id", None)` when necessary.
- Annotate mutable class constants with `ClassVar` to satisfy Ruff `RUF012`.
- Match overridden parameter names exactly, for example `disconnect(self, code)`.
- Cast ASGI callables and WebSocket route collections where Django and Channels type stubs disagree.

Do not change correct runtime behavior solely to silence a type warning without understanding the cause.

## 14. Important Implementation Details

- The actual turn fields are `round_number` and `turn_position`, not `round` and `position`.
- The genre enabled field is `is_enabled`.
- Player tokens are stored only as SHA-256 hashes.
- Leader votes are private. WebSocket voting progress must never expose voter or candidate IDs.
- Track metadata must not be broadcast before answer reveal.
- Host-only endpoints must continue filtering games with `host=request.user`.
- Spotify calls are currently synchronous `httpx` calls inside API views.
- The current local database is SQLite; PostgreSQL is planned before production.
- The Django server is the development server and is not production-ready.
- Redis database 0 is for Celery and database 1 is for Channels.
- Avoid mounting a host `.venv` over the container environment.

## 15. Immediate Next Tasks

Complete these in order:

### Task 1: Run and fix WebSocket tests

```bash
docker compose exec web python manage.py test games.test_consumers -v 2
```

Confirm all four tests pass. If they fail, inspect both the traceback and `games/consumers.py` before continuing.

### Task 2: Test the game-state endpoint

Add tests confirming:

- Unknown join tokens return 404.
- Lobby state contains no track answer.
- `TRACK_READY`, `PLAYING` and `AWAITING_ANSWER` states do not expose title, artist, album, artwork, Spotify ID or URI.
- `ANSWER_REVEALED` and `COMPLETED` include only the permitted answer fields.
- Scores and tie-aware ranks are correct.

### Task 3: Add a backend workflow integration test

Test the state transitions for:

```text
lobby open
→ player join
→ lobby closed
→ balanced teams
→ voting open
→ voting closed
→ game started
→ genre selected
→ track ready
→ playing
→ awaiting answer
→ answer revealed
→ score awarded
→ turn advanced or round completed
→ game finished
```

Mock Spotify HTTP calls and the Celery scheduling call. Do not make real Spotify requests in automated tests.

### Task 4: Run all backend validation

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py test -v 2
```

If Ruff and Pyright/Pylance commands are configured in `pyproject.toml`, run those as well.

### Task 5: Review permissions and error handling

- Verify every admin mutation requires authentication and ownership of the game.
- Verify every player mutation validates the player session token against the same game.
- Add rate limiting for join and WebSocket authentication attempts before public deployment.
- Decide whether public game state should require a joined-player token after registration closes.
- Add structured logging around Spotify failures and Celery task failures.

### Task 6: Begin the Nuxt frontend

Recommended frontend screen order:

1. QR/join page.
2. Player waiting room.
3. Admin lobby and team assignment controls.
4. Player team and leader-voting screen.
5. Admin game-control screen.
6. Active-team/genre screen.
7. Playback countdown and answer reveal screen.
8. Scoring and live leaderboard.
9. Round-complete and final-results screens.

The frontend should fetch the safe state endpoint on load, then open and authenticate its WebSocket. On reconnect, it should fetch state again instead of relying on missed events.

## 16. Production Work Deferred Until After the Frontend MVP

- Replace SQLite with PostgreSQL.
- Use a production ASGI server configuration.
- Configure HTTPS and secure `wss://` WebSockets.
- Set secure session and CSRF cookie options.
- Restrict allowed hosts, CORS origins and trusted CSRF origins.
- Store secrets in the deployment platform rather than a file.
- Add Redis authentication/network restrictions where appropriate.
- Add monitoring, structured logs and error reporting.
- Add database backups and migration deployment procedures.
- Add API throttling and WebSocket connection limits.
- Add CI to run checks and tests.

## 17. Recommended First Prompt for the Next LLM

Use this handoff together with the actual repository. A suitable continuation prompt is:

> Read `spotify_music_quiz_backend_handoff.md`, then inspect the current Django repository rather than assuming every conversational code snippet was saved exactly. Run the WebSocket consumer tests first. Preserve the finalized 0/1/3 scoring rule, keep Spotify answers hidden until `ANSWER_REVEALED`, and work step by step. Do not change models or endpoint contracts without explaining the migration or compatibility impact.

