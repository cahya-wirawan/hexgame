"""
Export DQN PyTorch checkpoints to ONNX so they can be run in the browser
via onnxruntime-web.

Usage (from repo root):
    python examples/export_dqn_onnx.py

Output files land in server/src/hexgame_server/static/models/,
which FastAPI serves at /models/<file>.

The browser hook (frontend/src/hooks/useDqnBot.ts) fetches the model from
/models/dqn_<size>x<size>.onnx and runs inference locally.
"""

import os
import sys

# Allow `from model_dqn import HexDQN` when run from repo root.
sys.path.insert(0, os.path.dirname(__file__))
# Allow `import hexgame.hex_engine` used by model_dqn.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client", "src"))

import torch

from model_dqn import HexDQN

SIZES = [5, 7, 9, 11, 13, 15]

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "server",
    "src",
    "hexgame_server",
    "static",
    "models",
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

for size in SIZES:
    pt_path = os.path.join(os.path.dirname(__file__), f"dqn_{size}x{size}.pt")
    if not os.path.exists(pt_path):
        print(f"  skip  dqn_{size}x{size}.pt — file not found")
        continue

    try:
        data = torch.load(pt_path, map_location="cpu", weights_only=True)
    except TypeError:
        data = torch.load(pt_path, map_location="cpu")

    net = HexDQN(size)
    net.load_state_dict(data["state_dict"])
    net.eval()

    dummy = torch.zeros(1, 2, size, size)
    onnx_path = os.path.join(OUTPUT_DIR, f"dqn_{size}x{size}.onnx")

    torch.onnx.export(
        net,
        dummy,
        onnx_path,
        input_names=["board"],
        output_names=["q_values"],
        dynamic_axes={"board": {0: "batch"}, "q_values": {0: "batch"}},
        opset_version=17,
    )

    size_kb = os.path.getsize(onnx_path) // 1024
    print(f"  ok    dqn_{size}x{size}.onnx  ({size_kb} KB) → {onnx_path}")

print("Done.")
