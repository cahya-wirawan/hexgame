"""Bundled example model agents.

Each module exposes ``agent(board, action_set)``. Add your own by dropping a
module here (or anywhere importable) and passing its name as ``--model-name``.
The client resolves ``--model-name NAME`` by importing ``hexgame.client.models.NAME``
first, then falling back to a plain top-level ``NAME`` on ``sys.path``.
"""
