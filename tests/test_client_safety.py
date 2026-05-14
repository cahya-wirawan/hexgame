import pytest

from hexgame.client_safety import (
    InvalidModelMove,
    MatchReplayLog,
    apply_server_move,
    board_for_model,
    model_move_to_payload,
    normalize_model_move,
)


class IndexableInt:
    def __init__(self, value):
        self.value = value

    def __index__(self):
        return self.value


class LegacyHexEngineModel:
    RED = 1
    BLUE = -1


class ServerNativeModel:
    RED = -1
    BLUE = 1


def test_normalize_model_move_accepts_legal_row_col_pair():
    assert normalize_model_move([1, 2], [(0, 0), (1, 2)]) == (1, 2)


def test_board_for_model_converts_legacy_hex_engine_encoding_without_mutating_source():
    board = [[-1, 0], [1, None]]

    converted = board_for_model(board, LegacyHexEngineModel)

    assert converted == [[1, 0], [-1, 0]]
    assert board == [[-1, 0], [1, None]]


def test_board_for_model_keeps_server_native_encoding():
    board = [[-1, 0], [1, None]]

    converted = board_for_model(board, ServerNativeModel)

    assert converted == [[-1, 0], [1, 0]]


def test_normalize_model_move_accepts_integer_like_coordinates():
    move = (IndexableInt(1), IndexableInt(2))

    assert normalize_model_move(move, [(1, 2)]) == (1, 2)


def test_normalize_model_move_rejects_boolean_coordinates():
    with pytest.raises(InvalidModelMove, match="coordinate must be an integer"):
        normalize_model_move((True, 0), [(1, 0)])


def test_normalize_model_move_rejects_occupied_or_out_of_set_move():
    with pytest.raises(InvalidModelMove, match="illegal move"):
        normalize_model_move((2, 2), [(0, 0), (1, 2)])


def test_normalize_model_move_rejects_bad_shape():
    with pytest.raises(InvalidModelMove, match="expected a \\(row, col\\) pair"):
        normalize_model_move(3, [(0, 0)])


def test_model_move_to_payload_adapts_row_col_to_q_r():
    assert model_move_to_payload((2, 4), [(2, 4)]) == {"q": 4, "r": 2}


def test_model_move_to_payload_rejects_q_r_order_mistake_when_cell_is_not_legal():
    legal_moves = [(2, 4)]

    with pytest.raises(InvalidModelMove, match="illegal move"):
        model_move_to_payload((4, 2), legal_moves)


def test_apply_server_move_validates_before_mutating_board():
    board = [[0, 0], [0, 0]]

    apply_server_move(board, q=1, r=0, player=-1)

    assert board == [[0, -1], [0, 0]]


def test_apply_server_move_rejects_occupied_local_cell():
    board = [[1, 0], [0, 0]]

    with pytest.raises(InvalidModelMove, match="occupied"):
        apply_server_move(board, q=0, r=0, player=-1)

    assert board == [[1, 0], [0, 0]]


def test_apply_server_move_rejects_invalid_player_without_mutating_board():
    board = [[0, 0], [0, 0]]

    with pytest.raises(InvalidModelMove, match="invalid player"):
        apply_server_move(board, q=1, r=1, player=2)

    assert board == [[0, 0], [0, 0]]


def test_apply_server_move_rejects_out_of_bounds_without_mutating_board():
    board = [[0, 0], [0, 0]]

    with pytest.raises(InvalidModelMove, match="outside local board"):
        apply_server_move(board, q=2, r=0, player=-1)

    assert board == [[0, 0], [0, 0]]


def test_match_replay_log_writes_json_lines(tmp_path):
    replay_path = tmp_path / "match.jsonl"
    replay = MatchReplayLog(replay_path)

    replay.record("model_move", raw_move=(1, 2), payload={"q": 2, "r": 1}, board=[[0, -1]])

    assert replay_path.read_text(encoding="utf-8").splitlines()[0].endswith(
        '"event":"model_move","raw_move":[1,2],"payload":{"q":2,"r":1},"board":[[0,-1]]}'
    )


def test_match_replay_log_auto_uses_replays_directory():
    replay = MatchReplayLog.create("auto", model_name="model_first", board_size=7, series_length=3)

    assert replay.path is not None
    assert replay.path.parent.as_posix() == "replays"
    assert "model_first_7x7_bo3" in replay.path.name


def test_match_replay_log_can_be_disabled(tmp_path):
    replay = MatchReplayLog.create("off", model_name="model_first", board_size=7, series_length=1)

    replay.record("ignored", path=tmp_path / "unused.jsonl")

    assert replay.path is None
