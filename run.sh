#!/usr/bin/env bash
# One-shot production run: builds the frontend and serves everything on :8000
set -e
cd "$(dirname "$0")"

if [ ! -f backend/data/fleetleads.db ] || [ ! -d frontend/dist ]; then
  echo "▶ Installing backend deps..."
  pip install -q -r backend/requirements.txt
  echo "▶ Building frontend..."
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

echo "▶ Starting FleetLeads on http://localhost:8000"
cd backend
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
