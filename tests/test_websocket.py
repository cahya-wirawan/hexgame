from fastapi.testclient import TestClient

from app.config import MAX_SLOTS, PLAYER_1, PLAYER_2
from app.main import app


def test_health_slots_and_overview():
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    slots = client.get("/slots").json()
    assert len(slots) == MAX_SLOTS
    assert slots[0]["state"] == "empty"
    response = client.get("/overview")
    assert response.status_code == 200
    assert "Hex Game Overview" in response.text


def test_two_clients_with_same_board_size_are_matched():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=11") as player_1:
        assert player_1.receive_json()["type"] == "joined"
        assert player_1.receive_json()["type"] == "waiting_for_opponent"

        with client.websocket_connect("/ws/matchmake?board_size=11") as player_2:
            joined_2 = player_2.receive_json()
            assert joined_2["type"] == "joined"
            assert joined_2["payload"]["player"] == PLAYER_2
            start_1 = player_1.receive_json()
            start_2 = player_2.receive_json()
            assert start_1["type"] == "game_start"
            assert start_1["payload"]["players"] == [PLAYER_1, PLAYER_2]
            assert start_2["type"] == "game_start"
            assert start_2["payload"]["players"] == [PLAYER_1, PLAYER_2]


def test_clients_with_different_board_sizes_do_not_share_slot():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=11") as player_1:
        player_1.receive_json()
        player_1.receive_json()

        with client.websocket_connect("/ws/matchmake?board_size=13") as player_2:
            joined_2 = player_2.receive_json()
            waiting_2 = player_2.receive_json()

            assert joined_2["payload"]["player"] == PLAYER_1
            assert joined_2["payload"]["slot_id"] == 2
            assert waiting_2["type"] == "waiting_for_opponent"


def test_clients_with_different_series_lengths_do_not_share_slot():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=11&series_length=3") as player_1:
        player_1.receive_json()
        player_1.receive_json()

        with client.websocket_connect("/ws/matchmake?board_size=11&series_length=5") as player_2:
            joined_2 = player_2.receive_json()
            waiting_2 = player_2.receive_json()

            assert joined_2["payload"]["player"] == PLAYER_1
            assert joined_2["payload"]["slot_id"] == 2
            assert joined_2["payload"]["series_length"] == 5
            assert waiting_2["type"] == "waiting_for_opponent"


def test_invalid_board_size_gets_structured_error():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=5") as websocket:
        message = websocket.receive_json()

    assert message == {"type": "error", "payload": {"message": "Unsupported board size"}}


def test_invalid_series_length_gets_structured_error():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=11&series_length=2") as websocket:
        message = websocket.receive_json()

    assert message == {"type": "error", "payload": {"message": "Unsupported series length"}}


def test_move_spoofing_is_ignored_and_authoritative_moves_are_broadcast():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()

            player_1.send_json({"type": "move", "payload": {"player": PLAYER_2, "q": 0, "r": 0}})
            move_for_1 = player_1.receive_json()
            move_for_2 = player_2.receive_json()

            assert move_for_1["type"] == "move"
            assert move_for_1["payload"]["player"] == PLAYER_1
            assert move_for_2["payload"]["player"] == PLAYER_1


def test_invalid_move_is_rejected():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()

            player_2.send_json({"type": "move", "payload": {"q": 0, "r": 0}})
            rejected = player_2.receive_json()

            assert rejected["type"] == "move_rejected"
            assert rejected["payload"]["reason"] == "Not your turn"


def test_game_over_is_emitted_for_player_1_win():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()

            player_1_moves = [(0, r) for r in range(7)]
            player_2_moves = [(6, r) for r in range(6)]

            for index, p1_move in enumerate(player_1_moves):
                player_1.send_json({"type": "move", "payload": {"q": p1_move[0], "r": p1_move[1]}})
                assert player_1.receive_json()["type"] == "move"
                assert player_2.receive_json()["type"] == "move"

                if index == len(player_1_moves) - 1:
                    game_over_1 = player_1.receive_json()
                    game_over_2 = player_2.receive_json()
                    assert game_over_1["type"] == "game_over"
                    assert game_over_1["payload"]["winner"] == PLAYER_1
                    assert game_over_2["type"] == "game_over"
                    break

                p2_move = player_2_moves[index]
                player_2.send_json({"type": "move", "payload": {"q": p2_move[0], "r": p2_move[1]}})
                assert player_1.receive_json()["type"] == "move"
                assert player_2.receive_json()["type"] == "move"


def test_best_of_three_continues_after_first_game_and_then_emits_series_over():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7&series_length=3") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7&series_length=3") as player_2:
            player_2.receive_json()
            first_start_1 = player_1.receive_json()
            first_start_2 = player_2.receive_json()
            assert first_start_1["payload"]["first_turn"] == PLAYER_1
            assert first_start_2["payload"]["wins_required"] == 2

            play_player_1_column_win(player_1, player_2)
            assert player_1.receive_json()["type"] == "game_over"
            assert player_2.receive_json()["type"] == "game_over"
            update_1 = player_1.receive_json()
            update_2 = player_2.receive_json()
            assert update_1["type"] == "series_update"
            assert update_1["payload"]["player_1_wins"] == 1
            assert update_2["payload"]["current_game_number"] == 2
            next_start_1 = player_1.receive_json()
            next_start_2 = player_2.receive_json()
            assert next_start_1["type"] == "game_start"
            assert next_start_1["payload"]["first_turn"] == PLAYER_2
            assert next_start_2["payload"]["current_game_number"] == 2

            player_2.send_json({"type": "move", "payload": {"q": 6, "r": 6}})
            assert player_1.receive_json()["type"] == "move"
            assert player_2.receive_json()["type"] == "move"

            play_player_1_column_win(player_1, player_2, player_2_already_moved=True)
            assert player_1.receive_json()["type"] == "game_over"
            assert player_2.receive_json()["type"] == "game_over"
            assert player_1.receive_json()["type"] == "series_update"
            assert player_2.receive_json()["type"] == "series_update"
            series_over_1 = player_1.receive_json()
            series_over_2 = player_2.receive_json()
            assert series_over_1["type"] == "series_over"
            assert series_over_1["payload"]["winner"] == PLAYER_1
            assert series_over_2["payload"]["player_1_wins"] == 2


def play_player_1_column_win(player_1, player_2, player_2_already_moved=False):
    player_1_moves = [(0, r) for r in range(7)]
    player_2_moves = [(6, r) for r in range(6)]
    player_2_move_index = 0

    for index, p1_move in enumerate(player_1_moves):
        player_1.send_json({"type": "move", "payload": {"q": p1_move[0], "r": p1_move[1]}})
        assert player_1.receive_json()["type"] == "move"
        assert player_2.receive_json()["type"] == "move"

        if index == len(player_1_moves) - 1:
            return

        p2_move = player_2_moves[player_2_move_index]
        player_2_move_index += 1
        player_2.send_json({"type": "move", "payload": {"q": p2_move[0], "r": p2_move[1]}})
        assert player_1.receive_json()["type"] == "move"
        assert player_2.receive_json()["type"] == "move"


def test_disconnect_notifies_opponent_and_resets_slot():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()
        disconnected = player_1.receive_json()
        assert disconnected["type"] == "opponent_disconnected"

    slots = client.get("/slots").json()
    assert slots[0]["state"] == "empty"
