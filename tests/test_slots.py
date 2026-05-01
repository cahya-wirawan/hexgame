import pytest

from app.config import PLAYER_1, PLAYER_2
from app.slots import SlotManager


@pytest.mark.asyncio
async def test_empty_slot_can_be_assigned_board_size():
    manager = SlotManager(max_slots=1)

    assignment = await manager.join_slot(object(), 11)
    snapshot = await manager.snapshot()

    assert assignment is not None
    assert assignment.player_id == PLAYER_1
    assert snapshot[0]["state"] == "waiting"
    assert snapshot[0]["board_size"] == 11


@pytest.mark.asyncio
async def test_client_joins_waiting_slot_with_same_board_size():
    manager = SlotManager(max_slots=1)

    first = await manager.join_slot(object(), 11)
    second = await manager.join_slot(object(), 11)
    snapshot = await manager.snapshot()

    assert first is not None
    assert second is not None
    assert second.player_id == PLAYER_2
    assert snapshot[0]["state"] == "full"
    assert snapshot[0]["player_count"] == 2


@pytest.mark.asyncio
async def test_client_does_not_join_waiting_slot_with_different_board_size():
    manager = SlotManager(max_slots=2)

    first = await manager.join_slot(object(), 11)
    second = await manager.join_slot(object(), 13)
    snapshot = await manager.snapshot()

    assert first is not None
    assert second is not None
    assert second.slot_id != first.slot_id
    assert snapshot[0]["board_size"] == 11
    assert snapshot[1]["board_size"] == 13


@pytest.mark.asyncio
async def test_full_slot_is_not_joinable_when_no_empty_slot_exists():
    manager = SlotManager(max_slots=1)

    await manager.join_slot(object(), 11)
    await manager.join_slot(object(), 11)
    third = await manager.join_slot(object(), 11)

    assert third is None


@pytest.mark.asyncio
async def test_slot_resets_after_disconnect():
    manager = SlotManager(max_slots=1)

    await manager.join_slot(object(), 11)
    remaining = await manager.reset_slot(1, expected_player_id=PLAYER_1)
    snapshot = await manager.snapshot()

    assert remaining is None
    assert snapshot[0]["state"] == "empty"
    assert snapshot[0]["board_size"] is None
