from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .config import PLAYER_1, PLAYER_2


@dataclass
class PlayerConnection:
    websocket: WebSocket | None
    player_id: int
    color: str
    reconnect_token: str
    model_name: str | None = None
    username: str | None = None
    connected: bool = True
    disconnected_at: float | None = None


@dataclass
class HexGameState:
    board_size: int
    board: list[list[int | None]]
    current_turn: int = PLAYER_1
    winner: int | None = None
    move_count: int = 0

    @classmethod
    def create(cls, board_size: int, first_turn: int = PLAYER_1) -> "HexGameState":
        return cls(
            board_size=board_size,
            board=[[0 for _ in range(board_size)] for _ in range(board_size)],
            current_turn=first_turn,
        )


@dataclass
class MatchSeriesState:
    series_length: int = 1
    wins_required: int = 1
    player_1_wins: int = 0
    player_2_wins: int = 0
    current_game_number: int = 1
    series_winner: int | None = None
    initial_first_player: int = PLAYER_1

    @classmethod
    def create(cls, series_length: int, first_player: int = PLAYER_1) -> "MatchSeriesState":
        return cls(
            series_length=series_length,
            wins_required=(series_length // 2) + 1,
            initial_first_player=first_player,
        )

    def first_turn(self) -> int:
        # Odd games: initial_first_player starts; even games: the other player starts.
        if self.current_game_number % 2 == 1:
            return self.initial_first_player
        return PLAYER_2 if self.initial_first_player == PLAYER_1 else PLAYER_1

    def record_win(self, winner: int) -> None:
        if winner == PLAYER_1:
            self.player_1_wins += 1
        elif winner == PLAYER_2:
            self.player_2_wins += 1

        if self.player_1_wins >= self.wins_required:
            self.series_winner = PLAYER_1
        elif self.player_2_wins >= self.wins_required:
            self.series_winner = PLAYER_2


@dataclass
class GameSlot:
    slot_id: int
    board_size: int | None = None
    series_length: int | None = None
    player_1: PlayerConnection | None = None
    player_2: PlayerConnection | None = None
    state: str = "empty"
    game_id: str | None = None
    game_state: HexGameState | None = None
    series_state: MatchSeriesState | None = None

    def player_count(self) -> int:
        return int(self.player_1 is not None) + int(self.player_2 is not None)

    def connected_player_count(self) -> int:
        return sum(
            int(connection is not None and connection.connected)
            for connection in (self.player_1, self.player_2)
        )

    def get_connection(self, player_id: int) -> PlayerConnection | None:
        if player_id == PLAYER_1:
            return self.player_1
        if player_id == PLAYER_2:
            return self.player_2
        return None

    def opponent_id(self, player_id: int) -> int:
        return PLAYER_2 if player_id == PLAYER_1 else PLAYER_1

    def opponent_connection(self, player_id: int) -> PlayerConnection | None:
        return self.get_connection(self.opponent_id(player_id))

    def reset(self) -> None:
        self.board_size = None
        self.series_length = None
        self.player_1 = None
        self.player_2 = None
        self.state = "empty"
        self.game_id = None
        self.game_state = None
        self.series_state = None

    def snapshot(self) -> dict[str, Any]:
        players = [
            connection.player_id
            for connection in (self.player_1, self.player_2)
            if connection is not None
        ]
        connected_players = [
            connection.player_id
            for connection in (self.player_1, self.player_2)
            if connection is not None and connection.connected
        ]
        disconnected_players = [
            connection.player_id
            for connection in (self.player_1, self.player_2)
            if connection is not None and not connection.connected
        ]
        player_models = {
            str(connection.player_id): connection.model_name
            for connection in (self.player_1, self.player_2)
            if connection is not None and connection.model_name
        }
        player_usernames = {
            str(connection.player_id): connection.username
            for connection in (self.player_1, self.player_2)
            if connection is not None and connection.username
        }
        game_state = self.game_state
        series_state = self.series_state
        snapshot: dict[str, Any] = {
            "slot_id": self.slot_id,
            "state": self.state,
            "board_size": self.board_size,
            "series_length": self.series_length,
            "player_count": self.player_count(),
            "connected_player_count": self.connected_player_count(),
            "players": players,
            "player_models": player_models,
            "player_usernames": player_usernames,
            "connected_players": connected_players,
            "disconnected_players": disconnected_players,
            "current_turn": game_state.current_turn if game_state else None,
            "winner": game_state.winner if game_state else None,
            "move_count": game_state.move_count if game_state else 0,
            "board": game_state.board if game_state else None,
            "wins_required": series_state.wins_required if series_state else None,
            "current_game_number": series_state.current_game_number if series_state else None,
            "player_1_wins": series_state.player_1_wins if series_state else 0,
            "player_2_wins": series_state.player_2_wins if series_state else 0,
            "series_winner": series_state.series_winner if series_state else None,
        }
        return snapshot


@dataclass(frozen=True)
class SlotAssignment:
    slot_id: int
    player_id: int
    color: str
    board_size: int
    series_length: int
    reconnect_token: str
    opponent_connected: bool
    player_1: PlayerConnection | None = field(repr=False)
    player_2: PlayerConnection | None = field(repr=False)
