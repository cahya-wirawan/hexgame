from __future__ import annotations

import operator
from collections.abc import Iterable
from typing import Any


class InvalidModelMove(ValueError):
    pass


def normalize_model_move(move: Any, legal_moves: Iterable[tuple[int, int]]) -> tuple[int, int]:
    """Return a legal (row, col) move or raise a clear client-side error."""
    legal_set = set(legal_moves)
    if not isinstance(move, (tuple, list)) or len(move) != 2:
        raise InvalidModelMove(f"Model returned {move!r}; expected a (row, col) pair")

    row = _coerce_coordinate(move[0], "row")
    col = _coerce_coordinate(move[1], "col")
    normalized = (row, col)
    if normalized not in legal_set:
        raise InvalidModelMove(f"Model returned illegal move {normalized}; expected one of {len(legal_set)} legal cells")
    return normalized


def model_move_to_payload(move: Any, legal_moves: Iterable[tuple[int, int]]) -> dict[str, int]:
    """Convert a model (row, col) move to the server's {q, r} payload."""
    row, col = normalize_model_move(move, legal_moves)
    return {"q": col, "r": row}


def apply_server_move(board: list[list[int | None]], q: Any, r: Any, player: Any) -> None:
    """Apply a trusted server move defensively, so malformed messages do not corrupt local state."""
    row = _coerce_coordinate(r, "r")
    col = _coerce_coordinate(q, "q")
    if not board or not 0 <= row < len(board) or not 0 <= col < len(board[row]):
        raise InvalidModelMove(f"Server move outside local board: q={col}, r={row}")
    if board[row][col] != 0:
        raise InvalidModelMove(f"Server move targets occupied local cell: q={col}, r={row}")
    if player not in {-1, 1}:
        raise InvalidModelMove(f"Server move has invalid player id: {player!r}")
    board[row][col] = player


def _coerce_coordinate(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise InvalidModelMove(f"{name} coordinate must be an integer, got {value!r}")
    try:
        return operator.index(value)
    except TypeError as exc:
        raise InvalidModelMove(f"{name} coordinate must be an integer, got {value!r}") from exc
