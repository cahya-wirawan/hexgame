from app.config import PLAYER_1, PLAYER_2
from app.game import apply_move, check_winner
from app.models import HexGameState


def test_board_initializes_with_correct_size():
    state = HexGameState.create(7)

    assert len(state.board) == 7
    assert all(len(row) == 7 for row in state.board)
    assert state.current_turn == PLAYER_1


def test_move_validation_and_turn_order():
    state = HexGameState.create(7)

    accepted = apply_move(state, PLAYER_1, 3, 4)
    assert accepted.accepted
    assert state.board[4][3] == PLAYER_1
    assert state.current_turn == PLAYER_2

    wrong_turn = apply_move(state, PLAYER_1, 0, 0)
    assert not wrong_turn.accepted
    assert wrong_turn.reason == "Not your turn"

    occupied = apply_move(state, PLAYER_2, 3, 4)
    assert not occupied.accepted
    assert occupied.reason == "Cell already occupied"

    outside = apply_move(state, PLAYER_2, 99, 0)
    assert not outside.accepted
    assert outside.reason == "Move outside board"


def test_player_1_top_to_bottom_win_is_detected():
    board = [[None for _ in range(3)] for _ in range(3)]
    board[0][0] = PLAYER_1
    board[1][0] = PLAYER_1
    board[2][0] = PLAYER_1

    assert check_winner(board, 3, PLAYER_1)


def test_player_2_left_to_right_win_is_detected():
    board = [[None for _ in range(3)] for _ in range(3)]
    board[0][0] = PLAYER_2
    board[0][1] = PLAYER_2
    board[0][2] = PLAYER_2

    assert check_winner(board, 3, PLAYER_2)
