import sys
from pathlib import Path

# Ensure client/src is in sys.path for test discovery and execution
client_src = Path(__file__).resolve().parent.parent / "client" / "src"
if client_src.exists() and str(client_src) not in sys.path:
    sys.path.insert(0, str(client_src))
