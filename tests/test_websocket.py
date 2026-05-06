from fastapi.testclient import TestClient

from app.config import MAX_SLOTS, PLAYER_1, PLAYER_2
from app.main import app


def test_health_slots_landing_docs_and_overview():
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    slots = client.get("/slots").json()
    assert len(slots) == MAX_SLOTS
    assert slots[0]["state"] == "empty"
    root_response = client.get("/")
    assert root_response.status_code == 200
    assert "Hex Game Server" in root_response.text
    response = client.get("/overview")
    assert response.status_code == 200
    assert "Hex Game Server" in response.text
    docs_response = client.get("/docs")
    assert docs_response.status_code == 200
    assert "Hex Game Server" in docs_response.text
    assert "swagger-ui" not in docs_response.text
    api_docs_response = client.get("/api/docs")
    assert api_docs_response.status_code == 200
    assert "swagger-ui" in api_docs_response.text


def test_two_clients_with_same_board_size_are_matched_and_model_names_and_usernames_are_public():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=11&model_name=model_alpha&username=alice") as player_1:
        joined_1 = player_1.receive_json()
        assert joined_1["type"] == "joined"
        assert joined_1["payload"]["player"] == PLAYER_1
        assert joined_1["payload"]["color"] == "red"
        assert isinstance(joined_1["payload"]["reconnect_token"], str)
        assert player_1.receive_json()["type"] == "waiting_for_opponent"

        with client.websocket_connect("/ws/matchmake?board_size=11&model_name=human&username=bob") as player_2:
            joined_2 = player_2.receive_json()
            assert joined_2["type"] == "joined"
            assert joined_2["payload"]["player"] == PLAYER_2
            assert joined_2["payload"]["color"] == "blue"
            assert isinstance(joined_2["payload"]["reconnect_token"], str)
            start_1 = player_1.receive_json()
            start_2 = player_2.receive_json()
            assert start_1["type"] == "game_start"
            assert start_1["payload"]["players"] == [PLAYER_1, PLAYER_2]
            assert start_2["type"] == "game_start"
            assert start_2["payload"]["players"] == [PLAYER_1, PLAYER_2]

            slots = client.get("/slots").json()
            assert slots[0]["player_models"] == {str(PLAYER_1): "model_alpha", str(PLAYER_2): "human"}
            assert slots[0]["player_usernames"] == {str(PLAYER_1): "alice", str(PLAYER_2): "bob"}
            assert "reconnect_token" not in slots[0]


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


def test_client_can_join_specific_waiting_slot_and_inherits_series_rules():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=11&series_length=5") as player_1:
        joined_1 = player_1.receive_json()
        player_1.receive_json()

        with client.websocket_connect(
            f"/ws/join-slot?slot_id={joined_1['payload']['slot_id']}&model_name=human&username=bob"
        ) as player_2:
            joined_2 = player_2.receive_json()
            start_1 = player_1.receive_json()
            start_2 = player_2.receive_json()

            assert joined_2["type"] == "joined"
            assert joined_2["payload"]["player"] == PLAYER_2
            assert joined_2["payload"]["slot_id"] == joined_1["payload"]["slot_id"]
            assert joined_2["payload"]["board_size"] == 11
            assert joined_2["payload"]["series_length"] == 5
            assert start_1["payload"]["series_length"] == 5
            assert start_1["payload"]["wins_required"] == 3
            assert start_2["payload"]["board_size"] == 11
            assert client.get("/slots").json()[0]["player_models"][str(PLAYER_2)] == "human"
            assert client.get("/slots").json()[0]["player_usernames"][str(PLAYER_2)] == "bob"


def test_join_specific_slot_rejects_empty_slot():
    client = TestClient(app)

    with client.websocket_connect("/ws/join-slot?slot_id=1") as websocket:
        rejected = websocket.receive_json()

    assert rejected["type"] == "error"
    assert rejected["payload"]["message"] == "Slot is not waiting for an opponent"


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

            player_1_moves = [(q, 0) for q in range(7)]
            player_2_moves = [(q, 6) for q in range(6)]

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

            play_player_1_row_win(player_1, player_2)
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

            play_player_1_row_win(player_1, player_2, player_2_already_moved=True)
            assert player_1.receive_json()["type"] == "game_over"
            assert player_2.receive_json()["type"] == "game_over"
            assert player_1.receive_json()["type"] == "series_update"
            assert player_2.receive_json()["type"] == "series_update"
            series_over_1 = player_1.receive_json()
            series_over_2 = player_2.receive_json()
            assert series_over_1["type"] == "series_over"
            assert series_over_1["payload"]["winner"] == PLAYER_1
            assert series_over_2["payload"]["player_1_wins"] == 2


def test_player_can_keep_slot_after_series_over_and_wait_for_next_match():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7&series_length=1&model_name=keeper") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7&series_length=1&model_name=opponent") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()

            play_player_1_row_win(player_1, player_2)
            assert player_1.receive_json()["type"] == "game_over"
            assert player_2.receive_json()["type"] == "game_over"
            assert player_1.receive_json()["type"] == "series_update"
            assert player_2.receive_json()["type"] == "series_update"
            assert player_1.receive_json()["type"] == "series_over"
            assert player_2.receive_json()["type"] == "series_over"

            player_1.send_json({"type": "keep_slot", "payload": {}})
            kept = player_1.receive_json()
            waiting = player_1.receive_json()
            opponent_notice = player_2.receive_json()

            assert kept["type"] == "slot_kept"
            assert kept["payload"]["player"] == PLAYER_1
            assert kept["payload"]["series_length"] == 1
            assert "reconnect_token" in kept["payload"]
            assert waiting["type"] == "waiting_for_opponent"
            assert opponent_notice["type"] == "opponent_left_slot"

            slots = client.get("/slots").json()
            assert slots[0]["state"] == "waiting"
            assert slots[0]["players"] == [PLAYER_1]
            assert slots[0]["player_models"] == {str(PLAYER_1): "keeper"}
            assert slots[0]["player_1_wins"] == 0
            assert slots[0]["player_2_wins"] == 0


def test_player_can_keep_slot_after_opponent_disconnects_mid_match():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7&series_length=3&model_name=keeper") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7&series_length=3&model_name=opponent") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()

        disconnected = player_1.receive_json()
        assert disconnected["type"] == "opponent_disconnected"

        player_1.send_json({"type": "keep_slot", "payload": {}})
        kept = player_1.receive_json()
        waiting = player_1.receive_json()

        assert kept["type"] == "slot_kept"
        assert kept["payload"]["series_length"] == 3
        assert waiting["type"] == "waiting_for_opponent"

        slots = client.get("/slots").json()
        assert slots[0]["state"] == "waiting"
        assert slots[0]["players"] == [PLAYER_1]
        assert slots[0]["player_models"] == {str(PLAYER_1): "keeper"}


def play_player_1_row_win(player_1, player_2, player_2_already_moved=False):
    player_1_moves = [(q, 0) for q in range(7)]
    player_2_moves = [(q, 6) for q in range(6)]
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


def test_disconnect_notifies_opponent_and_holds_slot_for_reconnect():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        joined_1 = player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()
        disconnected = player_1.receive_json()
        assert disconnected["type"] == "opponent_disconnected"
        assert disconnected["payload"]["reason"] == "waiting_for_reconnect"
        assert disconnected["payload"]["reconnect_timeout_seconds"] > 0
        player_1.send_json({"type": "move", "payload": {"q": 0, "r": 0}})
        rejected = player_1.receive_json()
        assert rejected["type"] == "move_rejected"
        assert rejected["payload"]["reason"] == "Game paused for reconnect"

        slots = client.get("/slots").json()
        assert slots[0]["state"] == "full"
        assert slots[0]["connected_players"] == [PLAYER_1]
        assert slots[0]["disconnected_players"] == [PLAYER_2]
        assert "reconnect_token" not in slots[0]
        assert "reconnect_token" in joined_1["payload"]


def test_disconnected_client_can_reconnect_and_resume_game():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            joined_2 = player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()
            token = joined_2["payload"]["reconnect_token"]

        assert player_1.receive_json()["type"] == "opponent_disconnected"

        with client.websocket_connect(f"/ws/reconnect?slot_id=1&token={token}") as reconnected_player_2:
            reconnected = reconnected_player_2.receive_json()
            assert reconnected["type"] == "reconnected"
            assert reconnected["payload"]["player"] == PLAYER_2
            assert reconnected["payload"]["slot"]["connected_players"] == [PLAYER_1, PLAYER_2]

            opponent_notice = player_1.receive_json()
            assert opponent_notice["type"] == "opponent_reconnected"
            assert opponent_notice["payload"]["player"] == PLAYER_2

            player_1.send_json({"type": "move", "payload": {"q": 0, "r": 0}})
            assert player_1.receive_json()["type"] == "move"
            assert reconnected_player_2.receive_json()["type"] == "move"


def test_reconnect_with_invalid_token_is_rejected():
    client = TestClient(app)

    with client.websocket_connect("/ws/matchmake?board_size=7") as player_1:
        player_1.receive_json()
        player_1.receive_json()
        with client.websocket_connect("/ws/matchmake?board_size=7") as player_2:
            player_2.receive_json()
            player_1.receive_json()
            player_2.receive_json()

        assert player_1.receive_json()["type"] == "opponent_disconnected"
        with client.websocket_connect("/ws/reconnect?slot_id=1&token=wrong") as websocket:
            rejected = websocket.receive_json()
            assert rejected["type"] == "error"
            assert rejected["payload"]["message"] == "Invalid reconnect token"
