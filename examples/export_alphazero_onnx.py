"""
Export AlphaZero checkpoints to ONNX for browser inference.

Usage:
    python3.12 examples/export_alphazero_onnx.py

Outputs alphazero_NxN.onnx into server/src/hexgame_server/static/models/.
Input:  "board"         (1, 2, N, N) float32 — perspective-encoded board
Outputs:"policy_logits" (1, N²)       float32 — raw policy logits
        "value"         (1,)           float32 — position value ∈ [−1, +1]
"""
import os
import sys

import torch
import torch.nn as nn

EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(EXAMPLES_DIR)
MODELS_DIR   = os.path.join(REPO_ROOT, "server", "src", "hexgame_server", "static", "models")
SIZES        = [5, 7, 9, 11]


# ── Network definition (mirrors model_alphazero.py) ───────────────────────────
# Copied here so the export script does not depend on hex_engine imports.

class _ResBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(x + self.net(x))


class HexAlphaNet(nn.Module):
    def __init__(self, size: int, channels: int = 128, blocks: int = 5):
        super().__init__()
        self.size     = size
        self.channels = channels
        self.blocks   = blocks
        ch = channels

        self.stem = nn.Sequential(
            nn.Conv2d(2, ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(ch),
            nn.ReLU(inplace=True),
        )
        self.trunk = nn.Sequential(*[_ResBlock(ch) for _ in range(blocks)])
        self.policy_head = nn.Sequential(
            nn.Conv2d(ch, 2, kernel_size=1, bias=False),
            nn.BatchNorm2d(2),
            nn.ReLU(inplace=True),
            nn.Flatten(),
            nn.Linear(2 * size * size, size * size),
        )
        self.value_head = nn.Sequential(
            nn.Conv2d(ch, 1, kernel_size=1, bias=False),
            nn.BatchNorm2d(1),
            nn.ReLU(inplace=True),
            nn.Flatten(),
            nn.Linear(size * size, 256),
            nn.ReLU(inplace=True),
            nn.Linear(256, 1),
            nn.Tanh(),
        )

    def forward(self, x: torch.Tensor):
        feat = self.trunk(self.stem(x))
        return self.policy_head(feat), self.value_head(feat).squeeze(-1)


# ── Infer architecture from state_dict ───────────────────────────────────────

def _infer_arch(state_dict: dict) -> tuple[int, int]:
    channels = state_dict["stem.0.weight"].shape[0]
    blocks   = sum(1 for k in state_dict if k.startswith("trunk.") and k.endswith(".net.0.weight"))
    return int(channels), int(blocks)


def _torch_load(path: str) -> dict:
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


# ── Export ────────────────────────────────────────────────────────────────────

def export_size(n: int) -> None:
    pt_path = os.path.join(EXAMPLES_DIR, f"alphazero_{n}x{n}.pt")
    if not os.path.exists(pt_path):
        print(f"  Skip {n}×{n}: {pt_path} not found")
        return

    ckpt = _torch_load(pt_path)
    sd   = ckpt["state_dict"]

    channels = ckpt.get("channels")
    blocks   = ckpt.get("blocks")
    if channels is None or blocks is None:
        channels, blocks = _infer_arch(sd)

    net = HexAlphaNet(n, channels=channels, blocks=blocks)
    net.load_state_dict(sd)
    net.eval()

    dummy    = torch.zeros(1, 2, n, n)
    out_path = os.path.join(MODELS_DIR, f"alphazero_{n}x{n}.onnx")

    with torch.no_grad():
        torch.onnx.export(
            net,
            dummy,
            out_path,
            input_names=["board"],
            output_names=["policy_logits", "value"],
            opset_version=17,
        )

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    nparams = sum(v.numel() for v in sd.values())
    print(f"  alphazero_{n}x{n}.onnx  ({channels}ch×{blocks}b  {nparams/1e6:.2f}M params  {size_mb:.1f} MB)")


if __name__ == "__main__":
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"Exporting AlphaZero checkpoints → {MODELS_DIR}")
    for n in SIZES:
        export_size(n)
    print("Done.")
