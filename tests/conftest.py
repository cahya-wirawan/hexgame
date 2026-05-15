import pytest

from hexgame_server.main import _ip_slot_count, slot_manager


@pytest.fixture(autouse=True)
def reset_slots():
    for slot in slot_manager.slots.values():
        slot.reset()
    _ip_slot_count.clear()
    yield
    for slot in slot_manager.slots.values():
        slot.reset()
    _ip_slot_count.clear()
