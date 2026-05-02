from __future__ import annotations

from dataclasses import dataclass

from .config import PLAYER_1, PLAYER_2
from .models import HexGameState

DIRECTIONS = [
    (+1, 0),
    (-1, 0),
    (0, +1),
    (0, -1),
    (+1, -1),
    (-1, +1),
]


@dataclass(frozen=True)
class MoveResult:
    accepted: bool
    reason: str | None = None
    winner: int | None = None
    next_turn: int | None = None


def other_player(player_id: int) -> int:
    return PLAYER_2 if player_id == PLAYER_1 else PLAYER_1


def validate_move_payload(payload: object) -> tuple[int, int] | str:
    if not isinstance(payload, dict):
        return "Invalid move payload"
    q = payload.get("q")
    r = payload.get("r")
    if not isinstance(q, int) or not isinstance(r, int):
        return "Move coordinates must be integers"
    return q, r


def apply_move(game_state: HexGameState, player_id: int, q: int, r: int) -> MoveResult:
    if game_state.winner is not None:
        return MoveResult(False, "Game already finished")
    if game_state.current_turn != player_id:
        return MoveResult(False, "Not your turn")
    if not 0 <= q < game_state.board_size:
        return MoveResult(False, "Move outside board")
    if not 0 <= r < game_state.board_size:
        return MoveResult(False, "Move outside board")
    if game_state.board[r][q] != 0:
        return MoveResult(False, "Cell already occupied")

    game_state.board[r][q] = player_id
    game_state.move_count += 1

    if check_winner(game_state.board, game_state.board_size, player_id):
        game_state.winner = player_id
        return MoveResult(True, winner=player_id, next_turn=None)

    game_state.current_turn = other_player(player_id)
    return MoveResult(True, next_turn=game_state.current_turn)


def check_winner(board: list[list[int | None]], board_size: int, player: int) -> bool:
    visited: set[tuple[int, int]] = set()
    stack: list[tuple[int, int]] = []

    if player == PLAYER_1:
        for r in range(board_size):
            if board[r][0] == player:
                stack.append((0, r))
    else:
        for q in range(board_size):
            if board[0][q] == player:
                stack.append((q, 0))

    while stack:
        q, r = stack.pop()
        if (q, r) in visited:
            continue
        visited.add((q, r))

        if player == PLAYER_1 and q == board_size - 1:
            return True
        if player == PLAYER_2 and r == board_size - 1:
            return True

        for dq, dr in DIRECTIONS:
            nq, nr = q + dq, r + dr
            if 0 <= nq < board_size and 0 <= nr < board_size:
                if board[nr][nq] == player:
                    stack.append((nq, nr))

    return False
