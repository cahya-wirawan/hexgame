# hexgame — clients

Reference Hex game clients for the [`hexgame-server`](https://pypi.org/project/hexgame-server/) arena. Installing this package gives you the `hexgame` command with three subcommands:

```
hexgame random   # uniformly random legal moves (smoke/stress test)
hexgame play     # model-driven client (--model-name ...)
hexgame gui      # pygame GUI model client (requires the [gui] extra)
```

## Install

```bash
pip install hexgame            # random/model clients (websockets only)
pip install "hexgame[gui]"     # also the pygame GUI
```

`hexgame` only depends on `websockets` (and `pygame` for the GUI extra). It does **not** pull in FastAPI/uvicorn — install [`hexgame-server`](https://pypi.org/project/hexgame-server/) separately if you want to host your own arena.

## Quick start

By default the clients connect to the hosted arena `wss://hexgame.codingdojo.ai`:

```bash
hexgame play --model-name model_random --board-size 7
hexgame gui  --model-name human        --board-size 7
```

Point at your own server with `--server`:

```bash
hexgame gui --server ws://127.0.0.1:8000 --model-name human --board-size 7
```

See the [main repository README](https://github.com/cahya-wirawan/hexgame) for the full client documentation, model authoring guide, replay log format, and WebSocket protocol.
