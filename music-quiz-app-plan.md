# Browser-Based Team Music Quiz App — Product and Technical Plan

**Document status:** Initial planning baseline  
**Date:** 12 August 2026  
**Platform:** Browser-based application  

## 1. Product Summary

This product is a live, in-person team music quiz. Players join a game by scanning a QR code, are randomly placed into balanced teams, vote for a team leader, and take turns identifying songs. During a team's turn, its elected leader triggers a random genre selection. A centrally controlled Spotify device plays a ten-second song segment. The active team gives its answer verbally, and the administrator reveals the song and awards a preset number of points. A live leaderboard reflects the updated scores.

The first release should be a mobile-friendly web application rather than a native mobile app. Players should not need to install software or create permanent accounts.

## 2. Confirmed Product Decisions

The following decisions have been explicitly agreed:

- The product will be browser based.
- One central device will handle Spotify playback.
- The administrator chooses the number of teams.
- The system assigns players to teams randomly and as evenly as possible.
- Players vote within their assigned team to select their team leader.
- Only the active team can answer the song for its turn.
- The active team's leader triggers the random genre selection.
- The application selects a random song associated with the selected genre.
- The song plays for ten seconds on the central Spotify-playing device.
- The team attempts to identify the song title and artist.
- The administrator controls scoring.
- The administrator awards one of three preset scores: 5, 10, or 20 points.
- The leaderboard updates after points are awarded.

## 3. Product Goals

### 3.1 Primary goals

- Let a group join a game quickly through a shared QR code.
- Eliminate manual team selection through balanced random assignment.
- Encourage team participation through leader voting.
- Run a clear, fair, turn-based music quiz.
- Keep music playback and scoring under administrator control.
- Synchronize the current game state across all connected devices.
- Make the interface simple enough to use during a social event without instructions from technical staff.

### 3.2 MVP success criteria

The minimum viable product is successful when:

- An administrator can create and start a game.
- Players can scan the QR code and join using a display name.
- Players are assigned to balanced teams without manual intervention.
- Each team can elect one leader.
- The game can rotate through team turns reliably.
- A leader can trigger genre selection only during their team's turn.
- The central device can play and stop an eligible Spotify track after ten seconds.
- Song information stays hidden until the administrator reveals it.
- The administrator can award 5, 10, or 20 points.
- Every connected device receives current team, round, voting, and leaderboard information in near real time.
- The game can end and display final standings.

### 3.3 Out of scope for the first release

- Native iOS or Android applications.
- Separate Spotify playback on each player's phone.
- Automatic speech recognition or automatic answer marking.
- Public player profiles, social feeds, or permanent player accounts.
- Automated matchmaking between remote players.
- In-app purchases, subscriptions, or commercial streaming features.
- User-uploaded copyrighted music.
- Advanced tournament brackets.

## 4. User Roles and Permissions

### 4.1 Administrator / host

The administrator controls the game and central playback. The administrator can:

- Create a game room.
- Choose the number of teams.
- Display or share the QR code and join link.
- View the player waiting room.
- Close or reopen player registration.
- Start balanced team assignment.
- Start and monitor leader voting.
- Resolve exceptional game states if necessary.
- Start the main game after leaders have been elected.
- Connect the host's Spotify Premium account.
- See the hidden song title and artist.
- Reveal the answer to players.
- Award 5, 10, or 20 points to the active team.
- Skip an unavailable or unsuitable track.
- Advance to the next turn.
- Pause, resume, or end the game.
- View final standings.

Administrator actions must be protected by an authenticated host session or a strong private host token. Player-facing join links must not grant administrator privileges.

### 4.2 Player

A player can:

- Join an open game using its QR code or short link.
- Enter a display name.
- See their assigned team.
- Vote once for an eligible member of their team.
- See their team's elected leader.
- View the current active team, game phase, scores, and leaderboard.
- If elected leader, trigger genre selection when their team is active.

Players cannot award points, reveal answers, control Spotify, change teams, or perform administrator actions.

### 4.3 Team leader

The leader is a player with one additional game permission. During that leader's team turn, the leader can press the control that triggers the genre wheel. The backend, not the browser alone, must verify that the requester is the elected leader of the active team and that the game is in the correct phase.

## 5. Complete Game Flow

### Phase 1: Game creation

1. The administrator opens the application and creates a new game.
2. The administrator enters a game name if desired and chooses the number of teams.
3. The application creates a unique game room and a hard-to-guess join token.
4. The application generates a QR code containing the player join URL.
5. The administrator displays the QR code on the central screen.

### Phase 2: Player registration

1. A player scans the QR code.
2. The player opens the join page in a mobile browser.
3. The player enters a display name.
4. The server checks that registration is open and the name is acceptable.
5. The player is added to the waiting room.
6. All connected clients receive the updated player count.
7. The administrator closes registration when everyone has joined.

Recommended MVP behavior:

- Do not require email addresses or passwords from players.
- Store a private player session token in the browser so a refresh can reconnect the player.
- Allow duplicate names only if the interface clearly distinguishes them, or require names to be unique within a game.
- Allow the administrator to remove an accidental or inappropriate entry before team assignment.

### Phase 3: Balanced random team assignment

1. The administrator starts team assignment.
2. The backend securely shuffles the registered player list.
3. Players are assigned using a round-robin or smallest-team-first algorithm.
4. The size difference between the largest and smallest teams must never exceed one.
5. Team assignments are saved in a single database transaction.
6. Each player sees their team name, color, and teammates.

Example: 17 players and 4 teams should produce team sizes of 5, 4, 4, and 4.

### Phase 4: Leader voting

1. Voting opens after team assignment.
2. Each player sees only the eligible candidates in their own team.
3. Each player submits one vote.
4. A player cannot vote more than once unless the administrator explicitly resets the vote.
5. Votes remain private; interim totals should not be shown to players.
6. Voting closes automatically when all eligible players have voted or manually when the administrator closes it.
7. The highest-voted player becomes team leader.
8. If multiple candidates tie for first place, the server randomly selects one of the tied candidates.
9. The result is announced to the relevant team and administrator.

Recommended MVP default: permit players to vote for themselves. This rule can be changed before implementation if desired.

### Phase 5: Game preparation

1. The administrator authenticates the central device with Spotify.
2. The application verifies that playback is available.
3. The administrator confirms the game can start.
4. The backend determines the initial team order using a random shuffle.
5. The first team becomes active.

### Phase 6: Team turn and genre selection

1. All players see which team is active.
2. The active team's leader sees an enabled **Spin genre** button.
3. Other players see a waiting state.
4. When the leader presses the button, the backend validates the leader, active team, and phase.
5. The backend randomly selects one enabled genre.
6. The selected genre is broadcast to all clients and shown through a genre-wheel animation.

The server's selected result is authoritative. The wheel animation only presents that result and must not independently calculate it.

### Phase 7: Song selection and playback

1. The server selects an eligible track associated with the chosen genre.
2. It excludes tracks already used in the current game.
3. The administrator sees that a track is ready, but players do not see its title, artist, album art, or identifying metadata.
4. The central Spotify device starts playback.
5. A server-coordinated ten-second timer begins after playback is confirmed.
6. At ten seconds, playback pauses.
7. The application moves to the answer phase.

The MVP should support an administrator **Skip track** control for unavailable, unsuitable, explicit, duplicated, or instantly recognizable tracks. Explicit tracks should be excluded by default where Spotify metadata permits.

### Phase 8: Answer and scoring

1. Only the active team discusses and gives its answer verbally.
2. The administrator decides whether and how well the team answered.
3. The administrator presses **Reveal answer**.
4. The song title and artist become visible on the central display and player devices.
5. The administrator awards 5, 10, or 20 points, or chooses no points.
6. A score event is saved with the administrator, team, round, value, and timestamp.
7. The leaderboard updates immediately.
8. The administrator advances to the next team's turn.

### Phase 9: Rotation and game completion

1. Teams take turns according to the saved turn order.
2. After the final team completes a turn, the next round begins if the game has remaining rounds.
3. The administrator can end the game at any time.
4. When the game ends, the application displays final standings.
5. Teams with equal points share the same score position unless a separate tie-break round is introduced later.

## 6. Screens and User Experience

### 6.1 Administrator screens

1. **Host landing page** — create a game or resume an active hosted game.
2. **Create game** — game name, number of teams, and initial configuration.
3. **Waiting room** — QR code, join URL, player count, player list, registration controls.
4. **Team assignment overview** — teams, colors, members, and confirmation controls.
5. **Voting monitor** — voting progress per team without exposing individual votes.
6. **Spotify setup** — connection status, playback device, and readiness check.
7. **Game control dashboard** — active team, phase, round, hidden song details, timer, skip, reveal, scoring, and next-turn controls.
8. **Leaderboard** — live ranking and score history access.
9. **Final results** — winner, standings, and end-game summary.

### 6.2 Player screens

1. **Join game** — display-name form and game identity.
2. **Waiting room** — confirmation and number of joined players.
3. **Team reveal** — team name, color, and teammates.
4. **Leader voting** — candidate selection and vote confirmation.
5. **Voting result** — elected leader and waiting state.
6. **Game view** — active team, round, genre, playback countdown, reveal, and leaderboard.
7. **Leader control state** — genre-spin action visible only to the active leader.
8. **Final results** — winning team and complete standings.

### 6.3 UX principles

- Design mobile-first for player devices and responsive widescreen layouts for the host display.
- Use large touch targets, strong contrast, and short instructions.
- Do not rely on color alone to communicate team or game state.
- Disable actions that are not valid in the current phase and explain why.
- Confirm consequential administrator actions such as ending a game or resetting teams.
- Give clear reconnection feedback after a network interruption.
- Keep the central screen visually suitable for projection or television display.
- Ensure that hidden song metadata never appears in player page source, client state, notifications, or WebSocket messages before reveal.

## 7. Recommended Technical Architecture

The recommended stack matches the project owner's existing experience:

| Layer | Recommended technology | Purpose |
| --- | --- | --- |
| Player and administrator frontend | Nuxt 3, TypeScript, Composition API, Tailwind CSS | Responsive browser UI |
| Backend API | Django and Django REST Framework | Business rules, authentication, game commands, Spotify integration |
| Real-time communication | Django Channels and WebSockets | Live lobby, voting status, phase, timer, and leaderboard updates |
| Persistent database | PostgreSQL | Games, players, teams, votes, rounds, tracks, and scores |
| Fast transient state and messaging | Redis | Channel layer, short-lived locks, presence, and rate limiting |
| Music integration | Spotify Web API and Web Playback SDK | Track discovery and central playback control |
| QR code generation | Server or frontend QR library | Encode the game join URL |
| Deployment | Containerized frontend, backend, PostgreSQL, and Redis | Repeatable environments and production hosting |

### 7.1 High-level component interaction

1. Nuxt player clients send commands to Django over HTTPS and receive updates over secure WebSockets.
2. The Nuxt administrator client uses privileged API routes and connects the central browser to Spotify playback.
3. Django owns the authoritative game state and validates every state transition.
4. PostgreSQL stores durable game data and audit events.
5. Redis supports Django Channels and protects time-sensitive operations from duplicate execution.
6. Spotify provides catalog metadata and playback for the authenticated central host account.

### 7.2 Architectural principles

- The backend is authoritative for teams, votes, leaders, genres, turns, scores, and phase changes.
- Client animations never determine random results.
- State-changing requests must be idempotent or protected against double submission.
- Every WebSocket event should contain the game ID, phase, event type, server timestamp, and monotonically increasing state version.
- Clients that reconnect should retrieve a complete state snapshot before applying new events.
- Spotify credentials and refresh tokens must never be exposed to player clients.

## 8. Game State Machine

Suggested authoritative game states:

1. `LOBBY_OPEN`
2. `LOBBY_CLOSED`
3. `TEAMS_ASSIGNED`
4. `VOTING_OPEN`
5. `VOTING_CLOSED`
6. `SPOTIFY_SETUP`
7. `READY`
8. `GENRE_SELECTION`
9. `TRACK_LOADING`
10. `PLAYING_CLIP`
11. `AWAITING_ANSWER`
12. `ANSWER_REVEALED`
13. `SCORING`
14. `TURN_COMPLETE`
15. `PAUSED`
16. `FINISHED`

The API must reject commands that are invalid for the current state. For example, a score cannot be awarded before an answer is revealed, and a genre cannot be spun by a non-leader or inactive team.

## 9. Core Data Model

### 9.1 Game

- ID and public join token
- Name
- Administrator/host identity
- Status and state version
- Number of teams
- Registration-open flag
- Current round and current turn index
- Active team
- Spotify connection status and central device reference
- Creation, start, pause, finish, and expiration timestamps

### 9.2 Player

- ID
- Game
- Display name and normalized name
- Private session token hash
- Team
- Leader flag or leader relationship
- Connection/presence status
- Join and last-seen timestamps

### 9.3 Team

- ID
- Game
- Name, display order, and accessible color/theme
- Elected leader
- Current score, preferably derived from score events or maintained transactionally
- Turn-order position

### 9.4 Vote

- ID
- Game and team
- Voter player
- Candidate player
- Creation timestamp
- Unique constraint on voter per voting cycle

### 9.5 Genre

- ID
- Display name
- Spotify search or playlist strategy
- Enabled flag
- Explicit-content policy
- Optional market/locale settings

### 9.6 Round and turn

- Round ID and sequence number
- Turn ID and sequence number
- Active team and leader
- Selected genre
- Selected track
- Playback start position and timestamps
- State and completion reason

### 9.7 Track usage

- Spotify track ID and URI
- Title and artist metadata stored for audit and reveal
- Genre selection source
- Duration and explicit flag
- Used game/turn
- Playback start offset
- Skip reason if applicable

Song-identifying fields must be omitted from player-facing responses until the reveal state.

### 9.8 Score event

- ID
- Game, round, turn, and team
- Point value constrained to 5, 10, or 20; zero can be represented by no event or an explicit no-score outcome
- Administrator identity
- Reason or optional note
- Creation timestamp
- Reversal reference if score corrections are later supported

An append-only score ledger is preferable to directly editing totals because it creates an audit trail.

## 10. API and Real-Time Events

### 10.1 Indicative HTTP endpoints

- `POST /api/games` — create game.
- `GET /api/games/{joinToken}/public` — retrieve safe public game details.
- `POST /api/games/{joinToken}/join` — register player and issue session token.
- `POST /api/games/{id}/close-registration` — administrator only.
- `POST /api/games/{id}/assign-teams` — administrator only.
- `POST /api/games/{id}/voting/open` — administrator only.
- `POST /api/games/{id}/votes` — submit one team vote.
- `POST /api/games/{id}/voting/close` — administrator only.
- `POST /api/games/{id}/spotify/connect` — begin host OAuth flow.
- `POST /api/games/{id}/start` — start game.
- `POST /api/games/{id}/turns/{turnId}/spin` — active leader only.
- `POST /api/games/{id}/turns/{turnId}/play` — administrator or trusted central device.
- `POST /api/games/{id}/turns/{turnId}/skip` — administrator only.
- `POST /api/games/{id}/turns/{turnId}/reveal` — administrator only.
- `POST /api/games/{id}/turns/{turnId}/score` — administrator only; value must be 5, 10, or 20.
- `POST /api/games/{id}/next-turn` — administrator only.
- `POST /api/games/{id}/pause` — administrator only.
- `POST /api/games/{id}/finish` — administrator only.
- `GET /api/games/{id}/state` — role-filtered state snapshot.

Endpoint names can be adjusted during implementation; authorization and state-transition guarantees are mandatory.

### 10.2 Indicative WebSocket events

- `player.joined`
- `registration.closed`
- `teams.assigned`
- `voting.opened`
- `vote.progress`
- `leaders.selected`
- `game.started`
- `turn.started`
- `genre.selected`
- `track.ready`
- `playback.started`
- `playback.stopped`
- `answer.revealed`
- `score.awarded`
- `leaderboard.updated`
- `turn.completed`
- `game.paused`
- `game.finished`

Role-specific payload filtering is required. A player must never receive administrator-only track metadata before reveal.

## 11. Randomization and Fairness

### 11.1 Team assignment

- Use server-side cryptographically secure random shuffling where practical.
- Assign shuffled players round-robin across the configured team count.
- Reject configurations where the number of teams exceeds the number of joined players unless empty teams are intentionally allowed later.
- Persist assignments atomically so retries do not reshuffle an already confirmed game.

### 11.2 Leader-vote tie breaking

- Identify all candidates sharing the highest vote count.
- If there is more than one, randomly select from only those tied candidates.
- Record that the result was determined by a tie-break.

### 11.3 Genre selection

- Select only from enabled genres.
- Consider avoiding the same genre on consecutive turns.
- Log the selected genre and randomization event.

### 11.4 Song selection

- Exclude tracks already used in the current game.
- Prefer tracks that are playable in the host's market.
- Exclude explicit tracks by default.
- Apply a maximum number of selection retries before asking the administrator to retry or choose another genre.
- Do not expose the song query results to player clients.

## 12. Spotify Integration and Constraints

### 12.1 Recommended MVP approach

- The administrator connects one Spotify Premium account on the central device.
- Spotify playback occurs only on that device or its connected speaker.
- The application searches or selects an eligible track for the server-selected genre.
- Playback begins at a configured or randomly chosen valid offset.
- The application pauses after ten seconds.
- The title, artist, album art, and Spotify URI remain administrator-only until reveal.

### 12.2 Platform limitations

- Spotify's Web Playback SDK requires a Spotify Premium account.
- Playback-control API operations also require Premium.
- Spotify's `preview_url` field is deprecated, nullable, and unavailable for some tracks.
- Spotify states that audio preview clips cannot form a standalone service or product.
- Spotify places restrictions on commercial streaming integrations.
- Browser autoplay rules may require direct user interaction before the central device can start audio.
- Playback timing can be affected by device transfer, buffering, browser throttling, and network delay.

Therefore, the ten-second interval should begin from a confirmed playback event where possible, and the administrator should have manual pause and skip controls.

### 12.3 Track-source strategy

The genre-to-song mechanism must be tested with Spotify's current API behavior. Potential strategies include:

- Curated Spotify playlists maintained per genre.
- Administrator-managed lists of approved Spotify track IDs.
- Spotify catalog search constrained by genre terms, followed by filtering.

For a dependable MVP, curated playlists or approved track pools are recommended over unconstrained search. They reduce incorrect genre matches, unavailable songs, explicit content, and low-quality quiz selections.

### 12.4 Legal and commercial review

Before public or commercial release:

- Review the current Spotify Developer Terms and platform policies.
- Confirm whether the intended event, business model, and playback arrangement are permitted.
- Obtain legal advice about public performance and music licensing where appropriate.
- Consider properly licensed or commissioned audio clips if Spotify cannot support the production use case.

Relevant official documentation:

- [Spotify Web Playback SDK](https://developer.spotify.com/documentation/web-playback-sdk)
- [Spotify Web Playback SDK reference](https://developer.spotify.com/documentation/web-playback-sdk/reference)
- [Spotify Web API track endpoint](https://developer.spotify.com/documentation/web-api/reference/get-track)
- [Spotify start/resume playback endpoint](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback)

## 13. Authentication, Privacy, and Security

### 13.1 Administrator security

- Use a proper administrator account or a strong host-only session.
- Store Spotify OAuth tokens encrypted at rest where they must be persisted.
- Use Authorization Code with PKCE or the flow currently recommended by Spotify for the chosen architecture.
- Never place a Spotify client secret in browser code.
- Use short-lived access tokens and protected refresh-token handling.
- Require recent administrator authorization for destructive actions.

### 13.2 Player security

- Give each joining player a random private session token.
- Store only a hash of the token server-side where feasible.
- Prevent a player from impersonating another player or leader.
- Validate game membership and role on every command.
- Rate-limit join attempts, votes, spins, and reconnection calls.
- Sanitize display names and enforce length limits.
- Protect all state-changing endpoints against CSRF or use an appropriate token-based design.

### 13.3 Data protection

- Collect only the minimum data required for the game.
- Do not require email, date of birth, address, or other sensitive information for MVP players.
- Define a retention period for completed games and player display names.
- Allow administrators to delete completed game data.
- Provide a short privacy notice before joining.
- Avoid third-party analytics until consent and privacy requirements have been assessed.

### 13.4 Application security

- Use HTTPS and secure WebSockets in every non-local environment.
- Keep administrator and player API serializers separate.
- Protect against ID enumeration by using opaque public tokens.
- Validate all transitions on the backend.
- Use database constraints for unique votes and valid scores.
- Log privileged actions without logging secrets or Spotify tokens.
- Apply dependency scanning, security headers, input validation, and production secret management.

## 14. Reliability and Edge Cases

The MVP must define behavior for:

- A player refreshing or temporarily losing connection.
- The administrator refreshing the dashboard.
- Two players selecting the same display name.
- A player joining after registration has closed.
- Fewer players than selected teams.
- Players leaving after teams have been assigned.
- A leader disconnecting before or during a turn.
- Incomplete team voting.
- A tied leader vote.
- The leader pressing the genre button twice.
- Two requests arriving at nearly the same time.
- Spotify authentication expiring.
- No active Spotify device being available.
- Spotify playback failing or buffering.
- A track being unavailable in the host's market.
- The selected track being shorter than the requested playback offset plus ten seconds.
- The same track being selected twice.
- Explicit or unsuitable content.
- The administrator awarding points twice.
- An incorrect score requiring correction.
- The administrator pausing or ending the game unexpectedly.

Recommended behavior:

- Preserve the authoritative state on the server.
- Make commands idempotent using command IDs or state-version checks.
- Let disconnected clients restore their role-filtered state from a snapshot.
- Allow the administrator to appoint a replacement leader if necessary.
- Record score corrections as reversing and replacement events rather than silently editing history.
- Provide a safe manual fallback for Spotify playback and timer failures.

## 15. Non-Functional Requirements

### 15.1 Performance

- Common API requests should normally complete within 500 ms, excluding Spotify operations.
- Real-time game events should normally appear on connected devices within one second.
- The waiting room and game view should remain responsive for the expected event size.
- Initial capacity planning should assume at least 100 simultaneous players in one game, then adjust after actual requirements are confirmed.

### 15.2 Availability and recovery

- Persist all critical phase, team, vote-result, turn, and scoring changes.
- A server restart should not erase an active game's durable state.
- A central device refresh should restore the administrator to the current phase.
- Use automated database backups in production.

### 15.3 Accessibility

- Target WCAG 2.2 AA practices for contrast, keyboard navigation, focus states, labels, and motion controls.
- Provide text labels in addition to team colors.
- Respect reduced-motion preferences for the genre wheel and transitions.
- Make timers readable and not dependent on sound alone.

### 15.4 Browser support

- Prioritize current Chrome, Safari, Edge, and Firefox versions.
- Test player flows on current iOS Safari and Android Chrome.
- Test the central Spotify-playing experience on the chosen supported desktop browser.

### 15.5 Observability

- Use structured server logs with game IDs and command IDs.
- Track errors in joins, WebSocket connections, Spotify authentication, track selection, playback, voting, and scoring.
- Add health checks for the backend, database, Redis, and WebSocket service.
- Do not include song spoilers or authentication secrets in player-visible error messages.

## 16. Testing Plan

### 16.1 Unit tests

- Balanced assignment for many player/team combinations.
- Team-count validation.
- Vote uniqueness and vote eligibility.
- Vote winner and tie-break selection.
- Genre and track randomization filters.
- Turn-order rotation.
- Score-value validation.
- Game-state transition rules.
- Role and permission checks.
- Safe player-state serialization without hidden song metadata.

### 16.2 Integration tests

- Game creation through player join.
- Concurrent joins and duplicate names.
- Team assignment transaction behavior.
- Complete voting workflow.
- WebSocket broadcasts and reconnection snapshots.
- Spotify OAuth token lifecycle.
- Track selection, playback confirmation, timer, and pause flow.
- Score creation and live leaderboard updates.
- Administrator refresh and game resumption.

### 16.3 End-to-end tests

- Administrator plus multiple simulated mobile players.
- QR join through final results.
- Active leader authorization.
- Invalid actions from non-active teams.
- Network interruption and reconnection.
- Spotify unavailability and track skip.
- Duplicate button presses and idempotency.

### 16.4 Manual event testing

Before release, run at least one full rehearsal using:

- The intended central laptop/browser and speakers.
- Several iPhones and Android phones.
- The actual venue network or a comparable Wi-Fi setup.
- Enough players to produce uneven team sizes.
- Spotify token expiry and playback failure scenarios.

## 17. Delivery Plan

### Phase 0: Requirements and design

- Confirm unresolved product decisions listed in Section 19.
- Choose a working product name and visual direction.
- Produce player and administrator wireframes.
- Define the state machine and permissions formally.
- Review Spotify feasibility and current developer policy.
- Create the initial backlog and acceptance criteria.

**Output:** approved product specification, wireframes, and technical design.

### Phase 1: Project foundation

- Create Nuxt 3 and Django projects.
- Configure PostgreSQL, Redis, Django Channels, and environment management.
- Establish local containers, linting, formatting, tests, and continuous integration.
- Implement base authentication and role separation.

**Output:** deployable development skeleton with automated checks.

### Phase 2: Lobby and team assignment

- Implement game creation.
- Generate QR code and join link.
- Build player registration and reconnection.
- Add waiting-room updates.
- Implement balanced random assignment.
- Build team-reveal interfaces.

**Output:** users can join and receive balanced teams.

### Phase 3: Voting and leadership

- Implement voting lifecycle and permissions.
- Add private votes and progress display.
- Implement tie handling.
- Save and announce leaders.

**Output:** every team can elect a leader reliably.

### Phase 4: Core round engine

- Implement the game state machine.
- Add turn order and active-team rotation.
- Implement server-authoritative genre selection.
- Build the leader and waiting interfaces.

**Output:** teams can take controlled turns and receive random genres.

### Phase 5: Spotify and ten-second playback

- Register and configure the Spotify developer application.
- Implement host OAuth and token handling.
- Build central-device readiness checks.
- Implement curated genre track pools.
- Add playback, ten-second pause, skip, retry, and failure handling.
- Confirm that player payloads do not leak hidden metadata.

**Output:** the central device can reliably conduct a ten-second music round.

### Phase 6: Reveal, scoring, and leaderboard

- Implement answer reveal.
- Add 5, 10, and 20 point controls.
- Create append-only score events.
- Build live leaderboard and final results.
- Add duplicate-score prevention and correction workflow.

**Output:** complete playable MVP loop.

### Phase 7: Hardening and release

- Complete automated and manual testing.
- Run accessibility and responsive-design checks.
- Conduct security and privacy review.
- Add monitoring, backups, and deployment documentation.
- Rehearse with real players and venue equipment.
- Fix launch-blocking issues.

**Output:** production-ready pilot release.

## 18. Initial Product Backlog

### Must have

- Game creation and secure host access.
- Configurable number of teams.
- QR code and mobile join flow.
- Balanced random assignment.
- Team leader voting.
- Active-team turn rotation.
- Server-authoritative genre selection.
- Central Spotify playback.
- Ten-second playback control.
- Answer reveal.
- Administrator scoring with 5, 10, or 20 points.
- Live leaderboard and final results.
- Reconnection and basic failure recovery.
- Prevention of role, answer, and score manipulation.

### Should have

- Curated genre/track administration.
- Track skip reasons.
- Score correction audit trail.
- Administrator pause/resume.
- Replacement leader controls.
- Explicit-content filtering.
- Reduced-motion support.
- Basic game history and summary.

### Could have after MVP

- Buzz-in mode for all teams.
- Automatic typed-answer evaluation.
- Configurable point presets.
- Multiple songs per turn.
- Difficulty levels based on clip offset or song popularity.
- Team avatars and custom names.
- Tie-break rounds.
- Event templates and reusable genre sets.
- Exportable results.
- Multiple languages.
- Licensed audio provider alternative.

## 19. Unresolved Decisions

These details have not yet been agreed and should be confirmed before or during wireframing:

1. Maximum and minimum number of teams.
2. Expected maximum number of players per game.
3. Whether players may vote for themselves as leader.
4. Whether voting closes automatically when everyone votes or only when the administrator closes it.
5. Number of rounds, fixed game length, or administrator-controlled ending.
6. Initial team order and whether it should be reshuffled each round.
7. Genre list and whether genres may repeat.
8. Whether the leader spins an animated wheel or presses a simple random-selection button.
9. Exact interpretation of 5, 10, and 20 points—for example, title only, artist only, both, speed, or administrator discretion.
10. Whether zero points should have an explicit button.
11. Whether the team submits an answer in the app or answers verbally to the administrator. The current recommendation is verbal answers for MVP.
12. Whether a clip starts at the beginning of a track or at a safe randomized offset.
13. Explicit-content policy.
14. Replacement behavior when an elected leader disconnects.
15. Score-correction rules.
16. Game-data retention period.
17. Whether the intended use is private, public, nonprofit, or commercial.
18. Hosting budget, target launch date, and expected event frequency.
19. Working product name, branding, and visual style.

## 20. Recommended Next Step

The next work item is to create low-fidelity wireframes for the administrator dashboard, game-creation screen, QR waiting room, player join flow, and team assignment screen. During that work, the unresolved rules that affect visible controls should be confirmed. After the wireframes are approved, the state machine and API contract can be finalized before implementation begins.

## 21. Definition of MVP Completion

The MVP is complete when an administrator can create a game, display a QR code, accept players, create balanced teams, run private leader voting, start a turn-based game, allow the active leader to trigger a random genre, play an eligible Spotify track for approximately ten seconds on one central device, reveal the title and artist, award 5, 10, or 20 points, rotate through teams, recover from ordinary refreshes, and finish with a synchronized final leaderboard—without exposing administrator controls or hidden song information to players.
