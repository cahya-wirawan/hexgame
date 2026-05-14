import pytest

from hexgame_server.main import slot_manager


@pytest.fixture(autouse=True)
def reset_slots():
    for slot in slot_manager.slots.values():
        slot.reset()
    yield
    for slot in slot_manager.slots.values():
        slot.reset()
