from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable
from typing import Any


class InvalidModelMove(ValueError):
    pass


class MatchReplayLog:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(
        cls,
        replay_log: str,
        *,
        model_name: str,
        board_size: int,
        series_length: int,
    ) -> "MatchReplayLog":
        if replay_log.lower() in {"off", "none", "false", "0"}:
            return cls(None)
        if replay_log != "auto":
            return cls(replay_log)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{timestamp}_{model_name}_{board_size}x{board_size}_bo{series_length}.jsonl"
        return cls(Path("examples") / "replays" / filename)

    def record(self, event: str, **fields: Any) -> None:
        if self.path is None:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **_jsonable(fields),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
