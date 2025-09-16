#!/usr/bin/env bash
set -e
if [ -f ".venv/bin/activate" ]; then source .venv/bin/activate; fi
(uvicorn app.web.main:app --host 0.0.0.0 --port 8080 &) && (python -m app.bot &)
echo "Both web (8080) and bot started in background."
