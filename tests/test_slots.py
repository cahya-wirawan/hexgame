import asyncio

from app.config import PLAYER_1, PLAYER_2
from app.slots import SlotManager


def run(coro):
    return asyncio.run(coro)


def test_empty_slot_can_be_assigned_board_size():
    async def scenario():
        manager = SlotManager(max_slots=1)

        assignment = await manager.join_slot(object(), 11)
        snapshot = await manager.snapshot()

        assert assignment is not None
        assert assignment.player_id == PLAYER_1
        assert snapshot[0]["state"] == "waiting"
        assert snapshot[0]["board_size"] == 11

    run(scenario())


def test_client_joins_waiting_slot_with_same_board_size():
    async def scenario():
        manager = SlotManager(max_slots=1)

        first = await manager.join_slot(object(), 11)
        second = await manager.join_slot(object(), 11)
        snapshot = await manager.snapshot()

        assert first is not None
        assert second is not None
        assert second.player_id == PLAYER_2
        assert snapshot[0]["state"] == "full"
        assert snapshot[0]["player_count"] == 2

    run(scenario())


def test_client_does_not_join_waiting_slot_with_different_board_size():
    async def scenario():
        manager = SlotManager(max_slots=2)

        first = await manager.join_slot(object(), 11)
        second = await manager.join_slot(object(), 13)
        snapshot = await manager.snapshot()

        assert first is not None
        assert second is not None
        assert second.slot_id != first.slot_id
        assert snapshot[0]["board_size"] == 11
        assert snapshot[1]["board_size"] == 13

    run(scenario())


def test_client_does_not_join_waiting_slot_with_different_series_length():
    async def scenario():
        manager = SlotManager(max_slots=2)

        first = await manager.join_slot(object(), 11, series_length=3)
        second = await manager.join_slot(object(), 11, series_length=5)
        snapshot = await manager.snapshot()

        assert first is not None
        assert second is not None
        assert second.slot_id != first.slot_id
        assert snapshot[0]["series_length"] == 3
        assert snapshot[1]["series_length"] == 5

    run(scenario())


def test_full_slot_is_not_joinable_when_no_empty_slot_exists():
    async def scenario():
        manager = SlotManager(max_slots=1)

        await manager.join_slot(object(), 11)
        await manager.join_slot(object(), 11)
        third = await manager.join_slot(object(), 11)

        assert third is None

    run(scenario())


def test_slot_marks_player_disconnected_without_exposing_token():
    async def scenario():
        manager = SlotManager(max_slots=1)

        first = await manager.join_slot(object(), 11)
        second = await manager.join_slot(object(), 11)
        remaining, token = await manager.mark_disconnected(1, PLAYER_2)
        snapshot = await manager.snapshot()

        assert first is not None
        assert second is not None
        assert remaining is not None
        assert remaining.player_id == PLAYER_1
        assert token
        assert snapshot[0]["state"] == "full"
        assert snapshot[0]["players"] == [PLAYER_1, PLAYER_2]
        assert snapshot[0]["connected_players"] == [PLAYER_1]
        assert snapshot[0]["disconnected_players"] == [PLAYER_2]
        assert "reconnect_token" not in snapshot[0]

    run(scenario())


def test_disconnected_player_can_reconnect_with_token():
    async def scenario():
        manager = SlotManager(max_slots=1)

        await manager.join_slot(object(), 11)
        await manager.join_slot(object(), 11)
        _, token = await manager.mark_disconnected(1, PLAYER_2)

        assignment, failure = await manager.reconnect_slot(object(), 1, token)
        snapshot = await manager.snapshot()

        assert failure is None
        assert assignment is not None
        assert assignment.player_id == PLAYER_2
        assert assignment.opponent_connected is True
        assert snapshot[0]["connected_players"] == [PLAYER_1, PLAYER_2]
        assert snapshot[0]["disconnected_players"] == []

    run(scenario())


def test_invalid_reconnect_token_is_rejected():
    async def scenario():
        manager = SlotManager(max_slots=1)

        await manager.join_slot(object(), 11)
        await manager.join_slot(object(), 11)
        await manager.mark_disconnected(1, PLAYER_2)

        assignment, failure = await manager.reconnect_slot(object(), 1, "wrong")

        assert assignment is None
        assert failure == "Invalid reconnect token"

    run(scenario())


def test_slot_resets_when_reconnect_timeout_expires():
    async def scenario():
        manager = SlotManager(max_slots=1)

        await manager.join_slot(object(), 11)
        await manager.join_slot(object(), 11)
        _, token = await manager.mark_disconnected(1, PLAYER_2)

        remaining = await manager.reset_if_still_disconnected(1, PLAYER_2, token)
        snapshot = await manager.snapshot()

        assert remaining is not None
        assert remaining.player_id == PLAYER_1
        assert snapshot[0]["state"] == "empty"
        assert snapshot[0]["board_size"] is None

    run(scenario())
