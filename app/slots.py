from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from .config import PLAYER_1, PLAYER_2, PLAYER_COLORS
from .models import GameSlot, HexGameState, PlayerConnection, SlotAssignment


class SlotManager:
    def __init__(self, max_slots: int = 5):
        self.slots = {
            slot_id: GameSlot(slot_id=slot_id)
            for slot_id in range(1, max_slots + 1)
        }
        self.lock = asyncio.Lock()

    async def join_slot(self, websocket: WebSocket, board_size: int) -> SlotAssignment | None:
        async with self.lock:
            slot = self._find_waiting_slot(board_size) or self._find_empty_slot()
            if slot is None:
                return None

            if slot.state == "empty":
                slot.board_size = board_size
                slot.player_1 = PlayerConnection(websocket, PLAYER_1, PLAYER_COLORS[PLAYER_1])
                slot.state = "waiting"
                return self._assignment(slot, PLAYER_1)

            if slot.state == "waiting" and slot.board_size == board_size and slot.player_2 is None:
                slot.player_2 = PlayerConnection(websocket, PLAYER_2, PLAYER_COLORS[PLAYER_2])
                slot.state = "full"
                slot.game_state = HexGameState.create(board_size)
                return self._assignment(slot, PLAYER_2)

            return None

    async def get_slot(self, slot_id: int) -> GameSlot | None:
        async with self.lock:
            return self.slots.get(slot_id)

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self.lock:
            return [slot.snapshot() for slot in self.slots.values()]

    async def reset_slot(self, slot_id: int, expected_player_id: str | None = None) -> PlayerConnection | None:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.state == "empty":
                return None

            if expected_player_id is not None and slot.get_connection(expected_player_id) is None:
                return None

            remaining: PlayerConnection | None = None
            if expected_player_id == PLAYER_1:
                remaining = slot.player_2
            elif expected_player_id == PLAYER_2:
                remaining = slot.player_1

            slot.reset()
            return remaining

    async def get_opponent(self, slot_id: int, player_id: str) -> PlayerConnection | None:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None:
                return None
            return slot.opponent_connection(player_id)

    async def apply_authoritative_move(self, slot_id: int, player_id: str, q: int, r: int):
        from .game import apply_move

        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None or slot.game_state is None or slot.state != "full":
                return None, "Game has not started"
            result = apply_move(slot.game_state, player_id, q, r)
            connections = [slot.player_1, slot.player_2]
            return (result, connections), None

    async def connections_for_slot(self, slot_id: int) -> list[PlayerConnection]:
        async with self.lock:
            slot = self.slots.get(slot_id)
            if slot is None:
                return []
            return [
                connection
                for connection in (slot.player_1, slot.player_2)
                if connection is not None
            ]

    def _find_waiting_slot(self, board_size: int) -> GameSlot | None:
        for slot in self.slots.values():
            if slot.state == "waiting" and slot.board_size == board_size and slot.player_2 is None:
                return slot
        return None

    def _find_empty_slot(self) -> GameSlot | None:
        for slot in self.slots.values():
            if slot.state == "empty":
                return slot
        return None

    def _assignment(self, slot: GameSlot, player_id: str) -> SlotAssignment:
        connection = slot.get_connection(player_id)
        if connection is None or slot.board_size is None:
            raise RuntimeError("slot assignment requested before player was assigned")
        return SlotAssignment(
            slot_id=slot.slot_id,
            player_id=player_id,
            color=connection.color,
            board_size=slot.board_size,
            opponent_connected=slot.player_1 is not None and slot.player_2 is not None,
            player_1=slot.player_1,
            player_2=slot.player_2,
        )
