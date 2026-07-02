from __future__ import annotations

import argparse

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain-sim")
    parser.add_argument("--version", action="version", version=f"brain-sim {__version__}")
    parser.parse_args(argv)
    return 0
