#!/usr/bin/env bash
set -euo pipefail

python -m examples.random_client --board-size 11 &
python -m examples.random_client --board-size 11 &
wait
