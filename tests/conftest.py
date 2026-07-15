import sys
from pathlib import Path

# document_logic.py is run directly as a script (see Makefile's `run` target),
# not imported as part of a package, so backend/services/ has to go on
# sys.path explicitly for tests to reach it the same way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "services"))
