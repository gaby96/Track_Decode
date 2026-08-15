export interface PublicGame {
  join_token: string;
  join_code: string;
  name: string;
  number_of_teams: number;
  rounds_per_team: number;
  status: string;
  registration_open: boolean;
  player_count: number;
}

export interface HostGame {
  id: string;
  join_token: string;
  join_code: string;
  name: string;
  number_of_teams: number;
  rounds_per_team: number;
  status: string;
  registration_open: boolean;
  current_round: number;
  host_username: string;
  spotify_device_id: string;
  spotify_device_name: string;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface PublicPlayer {
  id: string;
  display_name: string;
  team: string | null;
  team_name: string | null;
  is_connected: boolean;
  joined_at: string;
}

export interface PlayerJoinResponse {
  player: PublicPlayer;
  session_token: string;
}

export interface PlayerSessionStateResponse {
  player: PublicPlayer;
}

export interface TeamLeader {
  id: string;
  display_name: string;
}

export interface TeamMember {
  id: string;
  display_name: string;
}

export interface StandingsEntry {
  id: string;
  name: string;
  color: string;
  position: number;
  leader: TeamLeader | null;
  players: TeamMember[];
  total_points: number;
  rank: number;
}

export interface CurrentTurn {
  id: string;
  round_number: number;
  turn_position: number;
  status: string;
  team: {
    id: string;
    name: string;
    color: string;
  };
  genre: {
    id: string;
    name: string;
    color: string;
  } | null;
  track_ready: boolean;
  answer?: {
    title: string;
    artist: string;
    album: string;
    artwork_url: string;
  };
}

export interface GameStateResponse {
  game: {
    id: string;
    join_token: string;
    name: string;
    status: string;
    registration_open: boolean;
    number_of_teams: number;
    rounds_per_team: number;
    current_round: number;
    finished_at: string | null;
  };
  current_turn: CurrentTurn | null;
  standings: StandingsEntry[];
}

export interface VotingCandidatesResponse {
  game_status: string;
  team: {
    id: string;
    name: string;
    color: string;
  };
  player: PublicPlayer;
  candidates: PublicPlayer[];
  team_player_count: number;
  has_voted: boolean;
  requires_vote: boolean;
}

export interface StoredPlayerSession {
  sessionToken: string;
  player: PublicPlayer;
}
