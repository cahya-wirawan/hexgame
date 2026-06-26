from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from .config import REDIS_KEY_PREFIX, REDIS_LOCK_TIMEOUT_SECONDS, REDIS_URL
from .models import GameSlot, HexGameState, MatchSeriesState, PlayerConnection
from .slots import SlotManager

try:
    from redis import asyncio as redis_asyncio
except ImportError:  # pragma: no cover - exercised only when Redis backend is enabled without redis installed.
    redis_asyncio = None


class RedisSlotManager(SlotManager):
    """SlotManager with Redis persistence for slot, game, session, and reconnect-token state."""

    def __init__(
        self,
        max_slots: int = 5,
        redis_url: str = REDIS_URL,
        key_prefix: str = REDIS_KEY_PREFIX,
    ):
        super().__init__(max_slots=max_slots)
        if redis_asyncio is None:
            raise RuntimeError("HEX_STATE_BACKEND=redis requires the 'redis' Python package")
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.redis = redis_asyncio.from_url(redis_url, decode_responses=True)
        self.state_key = f"{key_prefix}:slots"
        self.lock_key = f"{key_prefix}:slots:lock"

    async def initialize(self) -> None:
        async with self._redis_lock():
            await self._hydrate_from_redis(mark_connections_disconnected=True)
            await self._persist_to_redis()

    async def close(self) -> None:
        await self.redis.close()

    async def join_slot(
        self,
        websocket: WebSocket,
        board_size: int,
        series_length: int = 1,
        model_name: str | None = None,
        username: str | None = None,
        first_player: int = -1,
    ):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            assignment = await super().join_slot(websocket, board_size, series_length, model_name, username, first_player=first_player)
            await self._persist_to_redis()
            return assignment

    async def join_slot_by_id(
        self,
        websocket: WebSocket,
        slot_id: int,
        model_name: str | None = None,
        username: str | None = None,
    ):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().join_slot_by_id(websocket, slot_id, model_name, username)
            await self._persist_to_redis()
            return result

    async def reconnect_slot(self, websocket: WebSocket, slot_id: int, token: str):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().reconnect_slot(websocket, slot_id, token)
            await self._persist_to_redis()
            return result

    async def reset_slot(self, slot_id: int, expected_player_id: int | None = None):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().reset_slot(slot_id, expected_player_id)
            await self._persist_to_redis()
            return result

    async def keep_slot_for_next_match(self, slot_id: int, player_id: int, reconnect_token: str):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().keep_slot_for_next_match(slot_id, player_id, reconnect_token)
            await self._persist_to_redis()
            return result

    async def mark_disconnected(
        self,
        slot_id: int,
        player_id: int,
        expected_reconnect_token: str | None = None,
    ):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().mark_disconnected(slot_id, player_id, expected_reconnect_token)
            await self._persist_to_redis()
            return result

    async def reset_if_still_disconnected(self, slot_id: int, player_id: int, reconnect_token: str):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().reset_if_still_disconnected(slot_id, player_id, reconnect_token)
            await self._persist_to_redis()
            return result

    async def apply_authoritative_move(self, slot_id: int, player_id: int, q: int, r: int):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().apply_authoritative_move(slot_id, player_id, q, r)
            await self._persist_to_redis()
            return result

    async def record_game_result(self, slot_id: int, winner: int):
        async with self._redis_lock():
            await self._hydrate_from_redis()
            result = await super().record_game_result(slot_id, winner)
            await self._persist_to_redis()
            return result

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self._redis_lock():
            await self._hydrate_from_redis()
            return await super().snapshot()

    async def snapshot_for_slot(self, slot_id: int) -> dict[str, Any] | None:
        async with self._redis_lock():
            await self._hydrate_from_redis()
            return await super().snapshot_for_slot(slot_id)

    def _redis_lock(self):
        return self.redis.lock(self.lock_key, timeout=REDIS_LOCK_TIMEOUT_SECONDS)

    async def _hydrate_from_redis(self, *, mark_connections_disconnected: bool = False) -> None:
        raw_state = await self.redis.get(self.state_key)
        if not raw_state:
            return

        state = json.loads(raw_state)
        slots = {}
        for slot_state in state.get("slots", []):
            current_slot = self.slots.get(slot_state["slot_id"])
            slot = self._slot_from_dict(
                slot_state,
                current_slot=current_slot,
                mark_connections_disconnected=mark_connections_disconnected,
            )
            slots[slot.slot_id] = slot

        for slot_id in self.slots:
            if slot_id in slots:
                self.slots[slot_id] = slots[slot_id]

    async def _persist_to_redis(self) -> None:
        state = {
            "version": 1,
            "slots": [self._slot_to_dict(slot) for slot in self.slots.values()],
        }
        await self.redis.set(self.state_key, json.dumps(state, separators=(",", ":")))

    def _slot_to_dict(self, slot: GameSlot) -> dict[str, Any]:
        return {
            "slot_id": slot.slot_id,
            "board_size": slot.board_size,
            "series_length": slot.series_length,
            "state": slot.state,
            "game_id": slot.game_id,
            "player_1": self._connection_to_dict(slot.player_1),
            "player_2": self._connection_to_dict(slot.player_2),
            "game_state": self._game_state_to_dict(slot.game_state),
            "series_state": self._series_state_to_dict(slot.series_state),
        }

    def _slot_from_dict(
        self,
        data: dict[str, Any],
        *,
        current_slot: GameSlot | None,
        mark_connections_disconnected: bool,
    ) -> GameSlot:
        slot = GameSlot(slot_id=data["slot_id"])
        slot.board_size = data.get("board_size")
        slot.series_length = data.get("series_length")
        slot.state = data.get("state", "empty")
        slot.game_id = data.get("game_id")
        slot.player_1 = self._connection_from_dict(
            data.get("player_1"),
            current_connection=current_slot.player_1 if current_slot else None,
            mark_connections_disconnected=mark_connections_disconnected,
        )
        slot.player_2 = self._connection_from_dict(
            data.get("player_2"),
            current_connection=current_slot.player_2 if current_slot else None,
            mark_connections_disconnected=mark_connections_disconnected,
        )
        slot.game_state = self._game_state_from_dict(data.get("game_state"))
        slot.series_state = self._series_state_from_dict(data.get("series_state"))
        return slot

    def _connection_to_dict(self, connection: PlayerConnection | None) -> dict[str, Any] | None:
        if connection is None:
            return None
        return {
            "player_id": connection.player_id,
            "color": connection.color,
            "reconnect_token": connection.reconnect_token,
            "model_name": connection.model_name,
            "username": connection.username,
            "connected": connection.connected,
            "disconnected_at": connection.disconnected_at,
        }

    def _connection_from_dict(
        self,
        data: dict[str, Any] | None,
        *,
        current_connection: PlayerConnection | None,
        mark_connections_disconnected: bool,
    ) -> PlayerConnection | None:
        if data is None:
            return None
        websocket = None
        if (
            current_connection is not None
            and current_connection.reconnect_token == data["reconnect_token"]
            and current_connection.websocket is not None
        ):
            websocket = current_connection.websocket
        return PlayerConnection(
            websocket=websocket,
            player_id=data["player_id"],
            color=data["color"],
            reconnect_token=data["reconnect_token"],
            model_name=data.get("model_name"),
            username=data.get("username"),
            connected=False if mark_connections_disconnected else data.get("connected", False),
            disconnected_at=data.get("disconnected_at"),
        )

    def _game_state_to_dict(self, game_state: HexGameState | None) -> dict[str, Any] | None:
        if game_state is None:
            return None
        return {
            "board_size": game_state.board_size,
            "board": game_state.board,
            "current_turn": game_state.current_turn,
            "winner": game_state.winner,
            "move_count": game_state.move_count,
        }

    def _game_state_from_dict(self, data: dict[str, Any] | None) -> HexGameState | None:
        if data is None:
            return None
        return HexGameState(
            board_size=data["board_size"],
            board=data["board"],
            current_turn=data["current_turn"],
            winner=data.get("winner"),
            move_count=data.get("move_count", 0),
        )

    def _series_state_to_dict(self, series_state: MatchSeriesState | None) -> dict[str, Any] | None:
        if series_state is None:
            return None
        return {
            "series_length": series_state.series_length,
            "wins_required": series_state.wins_required,
            "player_1_wins": series_state.player_1_wins,
            "player_2_wins": series_state.player_2_wins,
            "current_game_number": series_state.current_game_number,
            "series_winner": series_state.series_winner,
            "initial_first_player": series_state.initial_first_player,
        }

    def _series_state_from_dict(self, data: dict[str, Any] | None) -> MatchSeriesState | None:
        if data is None:
            return None
        return MatchSeriesState(
            series_length=data["series_length"],
            wins_required=data["wins_required"],
            player_1_wins=data.get("player_1_wins", 0),
            player_2_wins=data.get("player_2_wins", 0),
            current_game_number=data.get("current_game_number", 1),
            series_winner=data.get("series_winner"),
            initial_first_player=data.get("initial_first_player", -1),
        )
