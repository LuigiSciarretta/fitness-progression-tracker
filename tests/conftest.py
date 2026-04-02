from pathlib import Path
import sys

# Make project root importable when running `pytest` from repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
