"""Serve the local copy of the deployed frontend at http://localhost:3000."""
import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
FRONTEND = Path(__file__).resolve().parent / "frontend"

handler = functools.partial(SimpleHTTPRequestHandler, directory=str(FRONTEND))
print(f"Frontend: http://localhost:{PORT}", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
