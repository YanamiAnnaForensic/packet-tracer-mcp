"""Run from a Git checkout with only Python 3.10+; installation is optional."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from packet_tracer_mcp.__main__ import main

if __name__ == "__main__":
    main()
