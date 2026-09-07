# Nebius Personal AI — Hackathon Submission (Nebius x NVIDIA)

Brief overview
--------------
This project is a production-oriented Personal AI assistant built for the Personal AI Track. It runs a FastAPI backend that talks to NVIDIA Nemotron models via Nebius Token Factory (or Nebius AI Cloud). It stores short-term persistent memory per user, supports streaming responses for a low-latency UI, and is packaged so you can deploy on Nebius Serverless Endpoints or your own Kubernetes cluster.

Why this project (short, human):
- I chose the Personal AI Track because it showcases ownership of private data, persistent memory, and practical utility: an assistant that keeps context across sessions, runs on open infrastructure, and uses NVIDIA open-source models.
- The system is engineered for judges: it uses Nemotron models via Nebius, provides a responsive streaming UI, and includes production-ready deployment artifacts.

What’s included (high level)
- Backend: FastAPI app (app/main.py) — query and streaming endpoints.
- Model adapter: app/model_client.py — resilient HTTP client with streaming support.
- Prompting + safety: app/prompting.py — light PII checks and prompt builder.
- Persistence: app/db.py — async SQLAlchemy models (SQLite for local, switchable to Postgres).
- Minimal frontend: app/frontend (static HTML/CSS/vanilla JS) with streaming UI.
- Deployment assets: Dockerfile, docker-compose.yml, Kubernetes manifests, Nebius manifest template.
- Tests: tests/test_api.py with pytest + pytest-asyncio + httpx AsyncClient.
- This README and usage instructions for local testing and demo.

Folder structure
----------------
See FOLDER_STRUCTURE.txt for a full tree. Key items:
- app/main.py — FastAPI application with /api/v1/query and /api/v1/stream_query (SSE).
- app/model_client.py — HTTP + streaming adapter to Nebius model endpoints.
- app/prompting.py — helper to build prompts and minimal safety checks.
- app/frontend — static demo UI (no Node.js).
- tests — automated tests.

Prerequisites (local)
---------------------
- Python 3.10+ (3.11 recommended)
- Git, Docker (optional, recommended for local parity)
- (Optional) A Nebius API key for live model calls

Install locally
----------------
1. Clone
   git clone <this-repo>
   cd <this-repo>

2. Create virtualenv and install:
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   # dev/test deps
   pip install pytest pytest-asyncio httpx

3. Create a .env file from .env.example and adjust values:
   cp .env.example .env
   # edit .env to add your NEBIUS_API_KEY if you want live model calls

Run the server locally (two options)
-----------------------------------
Option A — quick local (no Docker)
- Ensure .env is set 
- Start:
  uvicorn app.main:app --host 0.0.0.0 --port 8080
- Open the demo UI at:
  http://localhost:8080/static/index.html

Option B — docker-compose (recommended if using Postgres)
- Build and run:
  docker-compose up --build
- The service will be available on port 8080.

Run tests
---------
Tests are small and mock model calls to run offline.

- Install test deps (if not already): pip install pytest pytest-asyncio httpx
- Run:
  pytest -q

Notes on tests
--------------
- tests/test_api.py starts an in-memory FastAPI test client and monkeypatches the model client so tests do not call external endpoints.
- The smoke-check in startup is non-fatal for local runs; tests rely on monkeypatching to avoid network calls.

##Thank you 
