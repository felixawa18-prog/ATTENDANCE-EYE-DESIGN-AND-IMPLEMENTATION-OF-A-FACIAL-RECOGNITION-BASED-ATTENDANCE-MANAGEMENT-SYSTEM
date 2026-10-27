#!/usr/bin/env bash
# Start the reconstructed backend (port 8000) and the local frontend copy (port 3000).
# Open http://localhost:3000 in Chrome or Firefox; press Ctrl+C to stop both.
set -e
cd "$(dirname "$0")"
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND=$!
trap 'kill $BACKEND' EXIT
.venv/bin/python serve_frontend.py 3000
