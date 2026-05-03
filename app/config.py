import os

MAX_SLOTS = 6
ALLOWED_BOARD_SIZES = {7, 9, 11, 13, 19}
ALLOWED_SERIES_LENGTHS = {1, 3, 5, 7, 9, 11, 13, 15}
PROTOCOL_VERSION = 1
RECONNECT_TIMEOUT_SECONDS = 30
STATE_BACKEND = os.getenv("HEX_STATE_BACKEND", "memory").strip().lower()
REDIS_URL = os.getenv("HEX_REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("HEX_REDIS_KEY_PREFIX", "hexgame")
REDIS_LOCK_TIMEOUT_SECONDS = float(os.getenv("HEX_REDIS_LOCK_TIMEOUT_SECONDS", "5"))
DATABASE_URL = os.getenv("HEX_DATABASE_URL")
DATABASE_AUTO_CREATE = os.getenv("HEX_DATABASE_AUTO_CREATE", "1").strip().lower() not in {"0", "false", "no"}

PLAYER_1 = -1
PLAYER_2 = 1
PLAYER_COLORS = {
    PLAYER_1: "red",
    PLAYER_2: "blue",
}
