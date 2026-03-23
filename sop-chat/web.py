"""Wonder SOPs — Web Interface."""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from loader import load_sops, _parse_frontmatter, SOP, _extract_summary
from search import SOPIndex
from chat import (
    build_context_block, build_interpreter_input, build_single_context,
    build_multi_context, parse_interpreter_response,
)
from prompts import INTERPRETER_PROMPT, PROMPT_A, PROMPT_B, ADMIN_SYSTEM_PROMPT, MODEL
from middleware import security_middleware, sanitize, MAX_MSG_LEN, MAX_BODY_LEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env file if present
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Paths
SOPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sops')
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'archive')
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')

# Load SOPs and build index once at startup
sops = load_sops()
index = SOPIndex(sops)

# Stats
_source_docs = set()
_total_pages = 0
for _s in sops:
    if _s.source_pdf:
        _source_docs.add(_s.source_pdf)
    _total_pages += _s.page_count
sop_stats = {
    "total_sops": len(sops),
    "source_documents": len(_source_docs),
    "total_pages": _total_pages,
}

# Anthropic client — lazy init
client: Optional[anthropic.AsyncAnthropic] = None

# Session stores
sessions: dict[str, list[dict]] = {}
admin_sessions: dict[str, list[dict]] = {}
admin_staged: dict[str, dict] = {}  # session_id -> {sop_id, body, is_new}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _next_sop_id() -> str:
    """Return the next available SOP-NNN ID."""
    existing = set()
    for s in sops:
        m = re.match(r'^SOP-(\d+)$', s.id)
        if m:
            existing.add(int(m.group(1)))
    i = 1
    while i in existing:
        i += 1
    return f"SOP-{i:03d}"


def _find_conflicts(proposed_body: str, exclude_id: str) -> list[dict]:
    """BM25 search for SOPs that might conflict with proposed changes."""
    if not proposed_body.strip():
        return []
    hits = index.search(proposed_body[:400])
    return [{"id": s.id, "title": s.title} for s in hits if s.id != exclude_id][:4]


def _ensure_client():
    global client
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        client = anthropic.AsyncAnthropic()
    return True


_SOP_ID_PATTERN = re.compile(r'\bSOP-(\d{1,4})\b', re.IGNORECASE)


def _detect_explicit_sop(message: str) -> Optional[str]:
    """If the user explicitly mentions a single SOP ID, return it."""
    matches = _SOP_ID_PATTERN.findall(message)
    if len(matches) == 1:
        return f"SOP-{int(matches[0]):03d}"
    return None


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI()
app.middleware("http")(security_middleware)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Public pages ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    with open(os.path.join(STATIC_DIR, "index.html")) as f:
        return f.read()

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open(os.path.join(STATIC_DIR, "admin.html")) as f:
        return f.read()

# ── SOP listing ──────────────────────────────────────────────────────────────

@app.get("/api/sops")
async def list_sops():
    return [{"id": s.id, "title": s.title, "summary": s.summary, "images": s.images} for s in sops]

@app.get("/api/sops/stats")
async def sops_stats():
    return sop_stats

# ── Regular chat (two-stage pipeline) ────────────────────────────────────────

def _stage2_stream(
    route: str,
    target_sops: list,
    message: str,
    history: list[dict],
    session_id: str,
) -> StreamingResponse:
    """Build context, select prompt, and stream Stage 2 response."""
    if route == "A" and target_sops:
        system_prompt = PROMPT_A
        context = build_single_context(target_sops[0])
    else:
        system_prompt = PROMPT_B
        context = build_multi_context(target_sops)

    source_ids = [s.id for s in target_sops]
    source_titles = [s.title for s in target_sops]

    augmented = f"{context}\n\nUser question: {message}"
    history.append({"role": "user", "content": f"User question: {message}"})
    trimmed = history[-100:]
    api_messages = trimmed[:-1] + [{"role": "user", "content": augmented}]

    async def generate():
        full_response = ""
        try:
            async with client.messages.stream(
                model=MODEL,
                system=system_prompt,
                messages=api_messages,
                max_tokens=1024,
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    yield f"data: {json.dumps(text)}\n\n"
        except Exception as e:
            logger.exception("Error during Claude stream")
            yield f"data: {json.dumps('[ERROR] ' + str(e))}\n\n"
            if history and history[-1]["role"] == "user":
                history.pop()
            yield "data: [DONE]\n\n"
            return

        history.append({"role": "assistant", "content": full_response})
        sources_payload = ",".join(
            f"{sid}|{title}" for sid, title in zip(source_ids, source_titles)
        )
        yield f"event: sources\ndata: {sources_payload}\n\n"
        yield f"event: session\ndata: {session_id}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = sanitize(body.get("message", "").strip())
    session_id = body.get("session_id", "")
    pinned_sop = body.get("pinned_sop", "")

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    if len(message) > MAX_MSG_LEN:
        return JSONResponse({"error": "Message too long"}, status_code=400)

    if not _ensure_client():
        return JSONResponse({"error": "ANTHROPIC_API_KEY not set"}, status_code=500)

    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = []

    history = sessions[session_id]

    # Short-circuit: pinned SOP
    if pinned_sop and re.match(r'^SOP-\d{1,4}$', pinned_sop):
        pinned = next((s for s in sops if s.id == pinned_sop), None)
        if pinned:
            logger.info("Short-circuit: pinned SOP %s → Route A", pinned_sop)
            return _stage2_stream("A", [pinned], message, history, session_id)

    # Short-circuit: explicit SOP ID in query
    explicit_id = _detect_explicit_sop(message)
    if explicit_id:
        explicit_sop = next((s for s in sops if s.id == explicit_id), None)
        if explicit_sop:
            logger.info("Short-circuit: explicit SOP %s → Route A", explicit_id)
            return _stage2_stream("A", [explicit_sop], message, history, session_id)

    # Stage 1: BM25 candidates + Interpreter
    candidates = index.search_summaries(message, top_k=8)
    interpreter_input = build_interpreter_input(message, candidates)

    logger.info("Stage 1: interpreting query (%d candidates)", len(candidates))
    try:
        interpreter_response = await client.messages.create(
            model=MODEL,
            system=INTERPRETER_PROMPT,
            messages=[{"role": "user", "content": interpreter_input}],
            max_tokens=200,
        )
        interpretation = parse_interpreter_response(
            interpreter_response.content[0].text
        )
        logger.info("Stage 1 result: route=%s, primary=%s, confidence=%s",
                     interpretation["route"], interpretation["primary_sop"],
                     interpretation["confidence"])
    except Exception:
        logger.exception("Stage 1 interpreter failed, falling back to BM25 top-1")
        interpretation = {
            "primary_sop": None, "secondary_sops": [],
            "route": "A", "confidence": "low", "intent": "",
        }

    # Router: pick SOPs and route
    route = interpretation["route"]
    primary_id = interpretation["primary_sop"]
    secondary_ids = interpretation["secondary_sops"]

    if route == "A" and primary_id:
        target_sops = index.get_sops_by_ids([primary_id])
        if not target_sops:
            target_sops = index.search(message, top_k=1)
    elif route == "B":
        all_ids = ([primary_id] if primary_id else []) + secondary_ids
        target_sops = index.get_sops_by_ids(all_ids)
        if not target_sops:
            target_sops = index.search(message, top_k=3)
    else:
        target_sops = index.search(message, top_k=1)
        route = "A"

    logger.info("Stage 2: route=%s, SOPs=%s", route, [s.id for s in target_sops])
    return _stage2_stream(route, target_sops, message, history, session_id)

# ── Admin chat ───────────────────────────────────────────────────────────────

@app.post("/api/admin/chat")
async def admin_chat(request: Request):
    body = await request.json()
    message = sanitize(body.get("message", "").strip())
    session_id = body.get("session_id", "")
    pinned_sop = body.get("pinned_sop", "")

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    if len(message) > MAX_MSG_LEN:
        return JSONResponse({"error": "Message too long"}, status_code=400)

    if not _ensure_client():
        return JSONResponse({"error": "ANTHROPIC_API_KEY not set"}, status_code=500)

    if not session_id or session_id not in admin_sessions:
        session_id = str(uuid.uuid4())
        admin_sessions[session_id] = []

    history = admin_sessions[session_id]

    sop_content_block = ""
    pinned_sop_id = ""
    if pinned_sop and re.match(r'^SOP-\d{1,4}$', pinned_sop):
        filepath = os.path.join(SOPS_DIR, f"{pinned_sop}.md")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
            _, body_text = _parse_frontmatter(raw)
            pinned_obj = next((s for s in sops if s.id == pinned_sop), None)
            title = pinned_obj.title if pinned_obj else pinned_sop
            sop_content_block = (
                f"<sop_content>\n--- {pinned_sop} | {title} ---\n{body_text}\n</sop_content>\n\n"
            )
            pinned_sop_id = pinned_sop

    retrieved = index.search(message)
    if pinned_sop_id:
        retrieved = [s for s in retrieved if s.id != pinned_sop_id][:5]
    context_block = build_context_block(retrieved) if retrieved else ""

    augmented = f"{sop_content_block}{context_block}\n\nAdmin request: {message}"
    history.append({"role": "user", "content": augmented})
    trimmed = history[-60:]

    async def generate():
        full_response = ""
        try:
            async with client.messages.stream(
                model=MODEL,
                system=ADMIN_SYSTEM_PROMPT,
                messages=trimmed,
                max_tokens=4096,
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    yield f"data: {json.dumps(text)}\n\n"
        except Exception as e:
            logger.exception("Error during admin Claude stream")
            yield f"data: {json.dumps('[ERROR] ' + str(e))}\n\n"
            if history and history[-1]["role"] == "user":
                history.pop()
            yield "data: [DONE]\n\n"
            return

        history.append({"role": "assistant", "content": full_response})

        proposal_match = re.search(
            r'\[\[PROPOSAL\]\]([\s\S]*?)\[\[/PROPOSAL\]\]', full_response
        )
        if proposal_match:
            proposed_body = sanitize(proposal_match.group(1).strip(), MAX_BODY_LEN)
            is_new = not bool(pinned_sop_id)
            admin_staged[session_id] = {
                "sop_id": pinned_sop_id or "",
                "body": proposed_body,
                "is_new": is_new,
            }
            conflicts = _find_conflicts(proposed_body, pinned_sop_id)
            yield f"event: proposal\ndata: {json.dumps({'sop_id': pinned_sop_id, 'is_new': is_new})}\n\n"
            yield f"event: conflicts\ndata: {json.dumps(conflicts)}\n\n"

        yield f"event: session\ndata: {session_id}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# ── Admin publish / cancel / archive ─────────────────────────────────────────

@app.post("/api/admin/publish")
async def admin_publish(request: Request):
    global index
    body = await request.json()
    session_id = body.get("session_id", "")

    if session_id not in admin_staged:
        return JSONResponse({"error": "No staged changes to publish"}, status_code=400)

    staged = admin_staged.pop(session_id)
    new_body = staged["body"]
    is_new = staged.get("is_new", False)

    if len(new_body) > MAX_BODY_LEN:
        return JSONResponse({"error": "Body too large"}, status_code=400)

    if is_new:
        new_id = _next_sop_id()
        filepath = os.path.join(SOPS_DIR, f"{new_id}.md")
        now = datetime.now(timezone.utc).isoformat()
        heading_match = re.search(r'^#+\s+(.+)$', new_body, re.MULTILINE)
        title = heading_match.group(1).strip() if heading_match else "New SOP"
        frontmatter = (
            f"---\nid: {new_id}\nsource_pdf: {title}\n"
            f"page_count: 1\nhas_tables: false\nocr_pages: []\n"
            f"converted_at: {now}\n---\n\n"
        )
        full_content = frontmatter + new_body + "\n"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)

        new_sop = SOP(
            id=new_id, title=title, body=new_body,
            summary=_extract_summary(new_body), source_pdf=title,
        )
        sops.append(new_sop)
        index = SOPIndex(sops)
        logger.info("Created new SOP: %s", new_id)
        return {"status": "created", "sop_id": new_id, "title": title}

    else:
        sop_id = staged["sop_id"]
        if not re.match(r'^SOP-\d{1,4}$', sop_id):
            return JSONResponse({"error": "Invalid SOP ID"}, status_code=400)
        filepath = os.path.join(SOPS_DIR, f"{sop_id}.md")
        if not os.path.exists(filepath):
            return JSONResponse({"error": "SOP not found"}, status_code=404)

        with open(filepath, 'r', encoding='utf-8') as f:
            existing = f.read()

        frontmatter_block = ""
        if existing.startswith('---'):
            parts = existing.split('---', 2)
            if len(parts) >= 3:
                frontmatter_block = f"---{parts[1]}---\n\n"

        new_content = frontmatter_block + new_body + "\n"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

        for s in sops:
            if s.id == sop_id:
                s.body = new_body
                s.summary = _extract_summary(new_body)
                break

        index = SOPIndex(sops)
        logger.info("Published edit to SOP: %s", sop_id)
        return {"status": "updated", "sop_id": sop_id}


@app.post("/api/admin/cancel")
async def admin_cancel(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    admin_staged.pop(session_id, None)
    return {"status": "cancelled"}


@app.get("/api/admin/next-id")
async def admin_next_id():
    return {"next_id": _next_sop_id()}


@app.post("/api/admin/archive")
async def admin_archive(request: Request):
    global index
    body = await request.json()
    sop_id = body.get("sop_id", "").strip()

    if not re.match(r'^SOP-\d{1,4}$', sop_id):
        return JSONResponse({"error": "Invalid SOP ID"}, status_code=400)

    src = os.path.join(SOPS_DIR, f"{sop_id}.md")
    if not os.path.exists(src):
        return JSONResponse({"error": "SOP not found"}, status_code=404)

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    dst = os.path.join(ARCHIVE_DIR, f"{sop_id}.md")
    os.rename(src, dst)

    removed = next((s for s in sops if s.id == sop_id), None)
    if removed:
        sops.remove(removed)
    index = SOPIndex(sops)

    logger.info("Archived SOP: %s", sop_id)
    return {"status": "archived", "sop_id": sop_id}

# ── Images ───────────────────────────────────────────────────────────────────

@app.get("/api/images/{filename}")
async def serve_image(filename: str):
    if '/' in filename or '\\' in filename or '..' in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "Image not found"}, status_code=404)
    return FileResponse(filepath)

# ── Clear session ────────────────────────────────────────────────────────────

@app.post("/api/clear")
async def clear_session(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    sessions.pop(session_id, None)
    admin_sessions.pop(session_id, None)
    admin_staged.pop(session_id, None)
    return {"status": "cleared"}

# ── Single SOP fetch ─────────────────────────────────────────────────────────

@app.get("/api/sops/{sop_id}")
async def get_sop(sop_id: str):
    if not re.match(r'^SOP-\d{1,4}$', sop_id):
        return JSONResponse({"error": "Invalid SOP ID"}, status_code=400)
    filepath = os.path.join(SOPS_DIR, f"{sop_id}.md")
    if not os.path.exists(filepath):
        return JSONResponse({"error": "SOP not found"}, status_code=404)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    _, body = _parse_frontmatter(content)
    title = next((s.title for s in sops if s.id == sop_id), sop_id)
    return {"id": sop_id, "title": title, "body": body}

# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
