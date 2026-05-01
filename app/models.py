from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .config import PLAYER_1, PLAYER_2


@dataclass
class PlayerConnection:
    websocket: WebSocket
    player_id: str
    color: str


@dataclass
class HexGameState:
    board_size: int
    board: list[list[str | None]]
    current_turn: str = PLAYER_1
    winner: str | None = None
    move_count: int = 0

    @classmethod
    def create(cls, board_size: int) -> "HexGameState":
        return cls(
            board_size=board_size,
            board=[[None for _ in range(board_size)] for _ in range(board_size)],
        )


@dataclass
class GameSlot:
    slot_id: int
    board_size: int | None = None
    player_1: PlayerConnection | None = None
    player_2: PlayerConnection | None = None
    state: str = "empty"
    game_id: str | None = None
    game_state: HexGameState | None = None

    def player_count(self) -> int:
        return int(self.player_1 is not None) + int(self.player_2 is not None)

    def get_connection(self, player_id: str) -> PlayerConnection | None:
        if player_id == PLAYER_1:
            return self.player_1
        if player_id == PLAYER_2:
            return self.player_2
        return None

    def opponent_id(self, player_id: str) -> str:
        return PLAYER_2 if player_id == PLAYER_1 else PLAYER_1

    def opponent_connection(self, player_id: str) -> PlayerConnection | None:
        return self.get_connection(self.opponent_id(player_id))

    def reset(self) -> None:
        self.board_size = None
        self.player_1 = None
        self.player_2 = None
        self.state = "empty"
        self.game_id = None
        self.game_state = None

    def snapshot(self) -> dict[str, Any]:
        players = [
            connection.player_id
            for connection in (self.player_1, self.player_2)
            if connection is not None
        ]
        game_state = self.game_state
        snapshot: dict[str, Any] = {
            "slot_id": self.slot_id,
            "state": self.state,
            "board_size": self.board_size,
            "player_count": self.player_count(),
            "players": players,
            "current_turn": game_state.current_turn if game_state else None,
            "winner": game_state.winner if game_state else None,
            "move_count": game_state.move_count if game_state else 0,
            "board": game_state.board if game_state else None,
        }
        return snapshot


@dataclass(frozen=True)
class SlotAssignment:
    slot_id: int
    player_id: str
    color: str
    board_size: int
    opponent_connected: bool
    player_1: PlayerConnection | None = field(repr=False)
    player_2: PlayerConnection | None = field(repr=False)
