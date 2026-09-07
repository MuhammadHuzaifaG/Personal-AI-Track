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
- Ensure .env is set as above (DATABASE_URL defaults to a local sqlite file).
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

Demo script for judges (what to record in a 2–3 minute video)
--------------------------------------------------------------
1. Show the README and architecture briefly (20s).
2. Start the server (uvicorn or docker-compose) and show logs initializing DB and model client smoke check (30s).
3. Open the UI at /static/index.html, type a prompt such as:
   "Plan a 30-minute focused study schedule to learn the basics of diffusion models."
   - Choose model hint "super" for normal, "ultra" for deep reasoning.
4. Show the assistant streaming the response in real time.
5. Show that responses are saved to memory (issue a follow-up question that references earlier response; the assistant uses memory).
6. Show the Nebius manifest and explain how it uses Nebius Token Factory and NVIDIA Nemotron models (brief).
7. Close with the judging criteria mapping below.

One-line run/setup guide
------------------------
Set NEBIUS_ENDPOINT and NEBIUS_API_KEY environment variables (or use .env), then:
uvicorn app.main:app --host 0.0.0.0 --port 8080

Mapping to judging criteria (explicit)
--------------------------------------
- Technological Implementation:
  - Uses Nebius Model endpoints through a resilient HTTP + streaming adapter.
  - Async IO, streaming, and persistent memory are implemented; production-ready deployment artifacts are included.
- Design:
  - Complete product experience: backend, streaming UI, memory, and deployment manifests.
  - UX is responsive via streaming; UI is simple, accessible, and deployable as static files.
- Potential Impact:
  - Personal assistant retains private data on user-owned infrastructure, enabling private workflows for professionals, students, and teams.
  - Can be extended to automate tasks or integrate with personal tools (calendar, email) while keeping data under user control.
- Quality of the Idea:
  - Non-obvious integration: streaming outputs, memory-first prompt composition, and model routing (nano/super/ultra) to optimize latency and cost.

Production checklist (before public deploy)
------------------------------------------
- Use managed Postgres in production (set DATABASE_URL to asyncpg Postgres).
- Store secrets (NEBIUS_API_KEY, DB URL) in a secrets manager — do not commit.
- Configure ALLOWED_ORIGINS to your UI domain.
- Add authentication and rate limiting.
- Swap in Redis for caching if high throughput and multiple instances.
- Add observability (metrics and tracing).

License and credits
-------------------
- Please include an appropriate open-source license when ready for public release.
- This project demonstrates use of NVIDIA Nemotron models via Nebius tokens as required by the hackathon.

If you’d like I will:
- Add a GitHub Actions job to run pytest in CI.
- Add an end-to-end test for the streaming endpoint.
- Replace the simple in-memory cache with Redis and provide config.

Thank you — tell me which CI or extra tests you want next and I’ll add them.