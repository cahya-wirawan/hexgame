import pytest

from examples.client_safety import InvalidModelMove, apply_server_move, normalize_model_move


def test_normalize_model_move_accepts_legal_row_col_pair():
    assert normalize_model_move([1, 2], [(0, 0), (1, 2)]) == (1, 2)


def test_normalize_model_move_rejects_occupied_or_out_of_set_move():
    with pytest.raises(InvalidModelMove, match="illegal move"):
        normalize_model_move((2, 2), [(0, 0), (1, 2)])


def test_normalize_model_move_rejects_bad_shape():
    with pytest.raises(InvalidModelMove, match="expected a \\(row, col\\) pair"):
        normalize_model_move(3, [(0, 0)])


def test_apply_server_move_validates_before_mutating_board():
    board = [[0, 0], [0, 0]]

    apply_server_move(board, q=1, r=0, player=-1)

    assert board == [[0, -1], [0, 0]]


def test_apply_server_move_rejects_occupied_local_cell():
    board = [[1, 0], [0, 0]]

    with pytest.raises(InvalidModelMove, match="occupied"):
        apply_server_move(board, q=0, r=0, player=-1)
