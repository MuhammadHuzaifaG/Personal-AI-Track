import os
import asyncio
import logging
import json
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from httpx import HTTPError

from .db import init_db, get_session
from .schemas import QueryRequest, QueryResponse
from .model_client import NebiusModelClient

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nebius_personal_ai")

app = FastAPI(title="Nebius Personal AI — Backend", version="0.1.0")

_allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
allow_origins = [_allowed_origins] if _allowed_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static frontend at /static
static_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

NEBIUS_ENDPOINT = os.getenv("NEBIUS_ENDPOINT", "https://api.nebius.example/v1/models/nemotron")
NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", None)
MODEL_REQUEST_TIMEOUT = int(os.getenv("MODEL_REQUEST_TIMEOUT", "60"))

model_client = NebiusModelClient(endpoint=NEBIUS_ENDPOINT, api_key=NEBIUS_API_KEY, timeout=MODEL_REQUEST_TIMEOUT)


@app.on_event("startup")
async def on_startup():
    logger.info("Starting Nebius Personal AI backend")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
        raise

    async def _smoke_check():
        try:
            await model_client.generate("Health check. Respond: ok.", model_hint="nano")
            logger.info("Model endpoint smoke check succeeded")
        except Exception as ex:
            logger.warning("Model endpoint smoke check failed: %s", ex)

    asyncio.create_task(_smoke_check())


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down Nebius Personal AI backend")
    try:
        client = getattr(model_client, "_client", None)
        if client is not None:
            await client.aclose()
            logger.info("Closed model HTTP client")
    except Exception:
        logger.exception("Error closing model HTTP client")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/query", response_model=QueryResponse)
async def query_assistant(req: QueryRequest, request: Request):
    logger.debug("Received query request (non-stream): user_id=%s model_hint=%s use_memory=%s", req.user_id, req.model_hint, req.use_memory)

    if not req.user_id or not req.prompt:
        logger.warning("Bad request: missing user_id or prompt")
        raise HTTPException(status_code=400, detail="user_id and prompt are required")

    memory_text = ""
    if req.use_memory:
        try:
            async with get_session() as session:
                stmt = text("SELECT content FROM memories WHERE user_id = :uid ORDER BY created_at DESC LIMIT 5")
                result = await session.execute(stmt, {"uid": req.user_id})
                fetched = result.fetchall()
                memory_text = "\n".join(r[0] for r in fetched) if fetched else ""
        except Exception:
            logger.exception("Failed to read memory; continuing without it")
            memory_text = ""

    prompt_context = f"MEMORY:\n{memory_text}\n\nUSER:\n{req.prompt}" if memory_text else req.prompt

    try:
        model_resp = await model_client.generate(prompt_context, model_hint=req.model_hint)
    except HTTPError:
        logger.exception("HTTP error while calling model")
        raise HTTPException(status_code=502, detail="model inference HTTP error")
    except Exception as e:
        logger.exception("Model inference failed: %s", e)
        raise HTTPException(status_code=502, detail=f"model inference failed: {str(e)}")

    if not getattr(model_resp, "text", None):
        logger.warning("Model returned empty response")
        raise HTTPException(status_code=502, detail="model returned empty response")

    async def save_memory_background(user_id: str, prompt_text: str, answer_text: str):
        try:
            async with get_session() as session:
                insert_stmt = text("INSERT INTO memories (user_id, content) VALUES (:uid, :content)")
                await session.execute(insert_stmt, {"uid": user_id, "content": f"Q: {prompt_text}\nA: {answer_text}"})
                await session.commit()
        except Exception:
            logger.exception("Failed to save memory in background")

    asyncio.create_task(save_memory_background(req.user_id, req.prompt, model_resp.text))

    return QueryResponse(reply=model_resp.text, model_used=getattr(model_resp, "model_name", None))


@app.post("/api/v1/stream_query")
async def stream_query(req: QueryRequest):
    """
    Streaming endpoint that yields Server-Sent-Event (SSE) style 'data: ...' frames.
    The frontend reads the response body incrementally and updates UI as chunks arrive.
    """
    logger.debug("Received streaming query request: user_id=%s model_hint=%s use_memory=%s", req.user_id, req.model_hint, req.use_memory)

    if not req.user_id or not req.prompt:
        logger.warning("Bad stream request: missing user_id or prompt")
        raise HTTPException(status_code=400, detail="user_id and prompt are required")

    async def event_generator() -> AsyncGenerator[str, None]:
        # fetch memory if requested
        memory_text = ""
        if req.use_memory:
            try:
                async with get_session() as session:
                    stmt = text("SELECT content FROM memories WHERE user_id = :uid ORDER BY created_at DESC LIMIT 5")
                    result = await session.execute(stmt, {"uid": req.user_id})
                    fetched = result.fetchall()
                    memory_text = "\n".join(r[0] for r in fetched) if fetched else ""
            except Exception:
                logger.exception("Failed to read memory for streaming request; continuing without memory")
                memory_text = ""

        prompt_context = f"MEMORY:\n{memory_text}\n\nUSER:\n{req.prompt}" if memory_text else req.prompt

        try:
            async for piece in model_client.stream_generate(prompt_context, model_hint=req.model_hint):
                # Each 'piece' is a partial string; emit as an SSE data field with JSON payload
                payload = {"chunk": piece}
                yield f"data: {json.dumps(payload)}\n\n"
            # Final event indicating completion
            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
            # Save memory in background after completion
            async def _save_mem():
                try:
                    async with get_session() as session:
                        insert_stmt = text("INSERT INTO memories (user_id, content) VALUES (:uid, :content)")
                        await session.execute(insert_stmt, {"uid": req.user_id, "content": f"Q: {req.prompt}\nA: [saved from stream]"})
                        await session.commit()
                except Exception:
                    logger.exception("Failed to save memory after streaming")
            asyncio.create_task(_save_mem())
        except Exception as e:
            logger.exception("Streaming inference failed: %s", e)
            err_payload = {"error": str(e)}
            yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")