"""
NebiusModelClient
- Async HTTP adapter for Nebius Token Factory / model endpoints.
- Provides generate() for full-response calls and stream_generate() async generator for streaming responses.
- Includes simple retry/backoff and an in-memory TTL cache for short-lived repeated prompts.
"""
import asyncio
import json
import logging
import hashlib
import time
from typing import Optional, AsyncGenerator, Dict, Any

import httpx
from pydantic import BaseModel

from .prompting import safety_check

logger = logging.getLogger("nebious_personal_ai.model_client")


class ModelResponse(BaseModel):
    text: str
    model_name: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class _SimpleTTLCache:
    """A tiny TTL cache safe for single-process use."""
    def __init__(self, ttl_seconds: int = 10, max_items: int = 1024):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self.store: Dict[str, Any] = {}
        self.lock = asyncio.Lock()

    async def get(self, key: str):
        async with self.lock:
            entry = self.store.get(key)
            if not entry:
                return None
            value, ts = entry
            if time.time() - ts > self.ttl:
                del self.store[key]
                return None
            return value

    async def set(self, key: str, value: Any):
        async with self.lock:
            if len(self.store) >= self.max_items:
                # naive eviction: pop oldest item
                oldest = min(self.store.items(), key=lambda kv: kv[1][1])[0]
                del self.store[oldest]
            self.store[key] = (value, time.time())


class NebiusModelClient:
    def __init__(
        self,
        endpoint: str,
        api_key: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        cache_ttl: int = 5,
    ):
        """
        endpoint: base HTTP endpoint. Can be a base URL like
          https://api.nebius.example/v1/models/
        or a model-specific path. The client will append typical inference paths if needed.
        api_key: bearer token for Nebius Token Factory or equivalent.
        """
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._client = httpx.AsyncClient(timeout=self.timeout)
        self._cache = _SimpleTTLCache(ttl_seconds=cache_ttl)
        # mapping hints to model names (tune these to your Nebius model naming)
        self.model_map = {
            "ultra": "nemotron-3-ultra",
            "super": "nemotron-super",
            "nano": "nemotron-nano",
            None: "nemotron-super",
            "default": "nemotron-super",
        }

    def _select_model(self, model_hint: Optional[str]) -> str:
        return self.model_map.get(model_hint, model_hint or self.model_map[None])

    def _build_url(self, path_suffix: str = "generate") -> str:
        """
        If endpoint already looks like a full generate path, return it as is.
        Otherwise append a conventional suffix. Common patterns:
          - /generate
          - /infer
          - /v1/generate
        """
        if any(part in self.endpoint for part in ["/generate", "/infer", "/complete", "/predict"]):
            return self.endpoint
        return f"{self.endpoint}/{path_suffix}"

    async def close(self):
        await self._client.aclose()

    async def _retry_request(self, func, *args, **kwargs):
        attempt = 0
        while True:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                attempt += 1
                if attempt > self.max_retries:
                    logger.exception("Max retries exceeded for model request")
                    raise
                backoff = self.backoff_base * (2 ** (attempt - 1))
                logger.warning("Model request failed (attempt %d/%d): %s; retrying in %.2fs", attempt, self.max_retries, e, backoff)
                await asyncio.sleep(backoff)

    async def generate(
        self,
        prompt: str,
        model_hint: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        use_cache: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ModelResponse:
        """
        Synchronous-style inference returning the completed text.

        - Runs a lightweight safety_check on the prompt.
        - Uses a short TTL cache to avoid re-sending identical prompts repeatedly.
        - Tries a few common response shapes when interpreting the server response.
        """
        safety_check(prompt)

        model_name = self._select_model(model_hint)
        url = self._build_url("generate")

        payload = {
            "model": model_name,
            "input": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra:
            payload.update(extra)

        cache_key = hashlib.sha256(json.dumps({"url": url, "payload": payload}, sort_keys=True).encode()).hexdigest()
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached:
                logger.debug("Cache hit for prompt (model=%s)", model_name)
                return ModelResponse(text=cached["text"], model_name=model_name, raw=cached.get("raw"))

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async def _do_post():
            logger.debug("POST %s (model=%s)", url, model_name)
            resp = await self._client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp

        resp = await self._retry_request(_do_post)

        # Attempt to interpret common response shapes
        text_output = ""
        raw_json = None
        try:
            raw_json = resp.json()
        except Exception:
            raw_json = None
        if isinstance(raw_json, dict):
            # common fields in various model servers
            if "output" in raw_json and isinstance(raw_json["output"], str):
                text_output = raw_json["output"]
            elif "result" in raw_json:
                # sometimes 'result' can be string or list
                if isinstance(raw_json["result"], list) and raw_json["result"]:
                    first = raw_json["result"][0]
                    if isinstance(first, dict) and "content" in first:
                        text_output = first["content"]
                    else:
                        text_output = str(first)
                elif isinstance(raw_json["result"], str):
                    text_output = raw_json["result"]
            elif "choices" in raw_json and isinstance(raw_json["choices"], list) and raw_json["choices"]:
                # openai-like shape
                first = raw_json["choices"][0]
                text_output = first.get("text") or first.get("message", {}).get("content") or ""
            elif "data" in raw_json and isinstance(raw_json["data"], list) and raw_json["data"]:
                # some servers return data -> list of outputs
                first = raw_json["data"][0]
                if isinstance(first, dict) and "text" in first:
                    text_output = first["text"]
                else:
                    text_output = str(first)
            else:
                # fallback: stringify the JSON
                text_output = json.dumps(raw_json)
        else:
            # fallback: raw text
            text_output = (await resp.aread()).decode(errors="ignore")

        if use_cache:
            await self._cache.set(cache_key, {"text": text_output, "raw": raw_json})

        return ModelResponse(text=text_output, model_name=model_name, raw=raw_json)

    async def stream_generate(
        self,
        prompt: str,
        model_hint: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
        extra: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens/partial output as they arrive.

        This method attempts to support both:
         - SSE-style streaming where each 'data:' line contains JSON
         - Chunked JSON lines where each line is a JSON partial
        """
        safety_check(prompt)

        model_name = self._select_model(model_hint)
        url = self._build_url("generate")

        payload = {
            "model": model_name,
            "input": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if extra:
            payload.update(extra)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.debug("Opening streaming request to %s (model=%s)", url, model_name)

        async def _do_stream():
            return await self._client.stream("POST", url, json=payload, headers=headers)

        # Single retry attempt for streaming (higher-level retries are complex for streaming)
        try:
            stream_ctx = await self._retry_request(_do_stream)
        except Exception:
            logger.exception("Streaming request failed")
            raise

        async with stream_ctx as resp:
            resp.raise_for_status()
            # Try to process stream as lines
            async for raw_line in resp.aiter_lines():
                if not raw_line:
                    continue
                # SSE format: "data: {...}" or "data: [..]"
                if raw_line.startswith("data:"):
                    data = raw_line[len("data:"):].strip()
                    if data == "[DONE]" or data == "done":
                        break
                    # some servers send a JSON object per data line
                    try:
                        parsed = json.loads(data)
                    except Exception:
                        # not JSON, emit raw data
                        yield data
                        continue
                    # Pull text out of common places
                    piece = ""
                    if isinstance(parsed, dict):
                        if "output" in parsed and isinstance(parsed["output"], str):
                            piece = parsed["output"]
                        elif "choices" in parsed and isinstance(parsed["choices"], list) and parsed["choices"]:
                            c = parsed["choices"][0]
                            piece = c.get("delta", {}).get("content") or c.get("text") or ""
                        elif "result" in parsed:
                            # result may be an array of partials
                            if isinstance(parsed["result"], list) and parsed["result"]:
                                first = parsed["result"][0]
                                piece = (first.get("content") if isinstance(first, dict) else str(first)) or ""
                    else:
                        piece = str(parsed)
                    if piece:
                        yield piece
                    continue

                # Otherwise try to parse line as JSON directly (chunked JSON streaming)
                try:
                    parsed = json.loads(raw_line)
                except Exception:
                    # if not JSON, yield the raw line as best-effort partial token
                    yield raw_line
                    continue

                # If parsed is dict, extract partial text fields
                text_piece = ""
                if isinstance(parsed, dict):
                    if "text" in parsed and isinstance(parsed["text"], str):
                        text_piece = parsed["text"]
                    elif "choices" in parsed and isinstance(parsed["choices"], list) and parsed["choices"]:
                        first = parsed["choices"][0]
                        text_piece = first.get("delta", {}).get("content") or first.get("text") or ""
                else:
                    text_piece = str(parsed)

                if text_piece:
                    yield text_piece

    # Placeholder for gRPC/Triton integration - implement this if you run Triton locally
    async def generate_triton(self, prompt: str, model_name: str, **kwargs) -> ModelResponse:
        """
        Implement Triton gRPC client here for ultra-low latency inference if needed.
        This project currently uses HTTP Token Factory endpoints; add Triton support later.
        """
        raise NotImplementedError("Triton gRPC integration not yet implemented")