"""Console entry point for the Hex game clients (``hexgame``).

Dispatches to one of the reference clients:

    hexgame random [options]   # uniformly random legal moves (smoke/stress test)
    hexgame play   [options]   # model-driven client (--model-name ...)
    hexgame gui    [options]   # pygame GUI model client (requires the [gui] extra)

Anything after the subcommand is forwarded verbatim to that client, so
``hexgame play --help`` shows the model client's own options.
"""

from __future__ import annotations

import importlib
import sys


_SUBCOMMANDS = {
    "random": ("hexgame.client.random_client", "uniformly random legal moves (smoke/stress test)"),
    "play": ("hexgame.client.model_client", "model-driven client (--model-name ...)"),
    "gui": ("hexgame.client.gui_client", "pygame GUI model client (needs the [gui] extra)"),
}


def _usage() -> str:
    lines = ["usage: hexgame {random,play,gui} [options]", "", "commands:"]
    width = max(len(name) for name in _SUBCOMMANDS)
    for name, (_, desc) in _SUBCOMMANDS.items():
        lines.append(f"  {name.ljust(width)}  {desc}")
    lines.append("")
    lines.append("Run 'hexgame <command> --help' for command-specific options.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        return
    command = argv[0]
    if command not in _SUBCOMMANDS:
        sys.stderr.write(f"hexgame: unknown command {command!r}\n\n{_usage()}\n")
        raise SystemExit(2)

    module_name, _ = _SUBCOMMANDS[command]
    module = importlib.import_module(module_name)
    module.main(argv[1:])


if __name__ == "__main__":
    main()
