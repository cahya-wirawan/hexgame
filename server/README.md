# hexgame-server — Hex game server

FastAPI WebSocket Hex game server with matchmaking, best-of series, server-authoritative gameplay, win detection, reconnect tokens, and an optional Redis/PostgreSQL state backend. Ships with a built-in Vite/React dashboard (`/`, `/docs`, `/overview`, `/statistics`).

Installing this package gives you the `hexgame-server` command.

## Install

```bash
pip install hexgame-server                    # core
pip install "hexgame-server[redis]"           # + Redis state backend
pip install "hexgame-server[postgres]"        # + PostgreSQL completed-series history
pip install "hexgame-server[all]"             # both backends
```

`hexgame-server` is independent from the [`hexgame`](https://pypi.org/project/hexgame/) client distribution — install that one as well only if you want to play against your own server from the same machine.

## Run

```bash
hexgame-server --host 0.0.0.0 --port 8000
# optional flags: --reload, --workers N (Redis backend required), --log-level info
```

Then open:

- Landing page: <http://127.0.0.1:8000/>
- Slot state JSON: <http://127.0.0.1:8000/slots>
- Overview dashboard: <http://127.0.0.1:8000/overview>
- Statistics leaderboard: <http://127.0.0.1:8000/statistics>

See the [main repository README](https://github.com/cahya-wirawan/hexgame) for the full server documentation, WebSocket protocol, deployment options (Docker), and design notes.
