#!/usr/bin/env bash
# Launch two random-move clients against a local server to play a full game.
set -euo pipefail

SERVER="${1:-ws://127.0.0.1:8000}"
BOARD_SIZE="${2:-11}"

hexgame random --server "$SERVER" --board-size "$BOARD_SIZE" --seed 1 &
hexgame random --server "$SERVER" --board-size "$BOARD_SIZE" --seed 2 &
wait
