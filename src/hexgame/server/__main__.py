"""Console entry point for the Hex game server (``hexgame-server``).

Thin wrapper around uvicorn so the package installs a real command. Equivalent
to ``python -m uvicorn hexgame.server.main:app`` with a few common flags.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="hexgame-server",
        description="Run the Hex game WebSocket server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="number of worker processes; use >1 only with HEX_STATE_BACKEND=redis",
    )
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    parser.add_argument("--log-level", default="info", help="uvicorn log level (default: info)")
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(
        "hexgame.server.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
