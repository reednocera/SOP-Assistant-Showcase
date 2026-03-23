"""Security middleware: basic auth, rate limiting, and HTTP security headers."""

import base64
import os
import re
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse, Response

# ── Config ───────────────────────────────────────────────────────────────────

BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USER", "wonder")
BASIC_AUTH_PASS = os.getenv("BASIC_AUTH_PASS", "")

# ── Input sanitization ───────────────────────────────────────────────────────

_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
MAX_MSG_LEN = 2000
MAX_BODY_LEN = 100_000  # 100 KB for SOP bodies


def sanitize(text: str, max_len: int = MAX_MSG_LEN) -> str:
    """Strip control characters and truncate."""
    text = _CONTROL_RE.sub('', text)
    return text[:max_len]


# ── Rate limiter ─────────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, max_requests: int = 20, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self._buckets: dict[str, list] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        self._buckets[key] = [t for t in bucket if now - t < self.window]
        if len(self._buckets[key]) >= self.max_requests:
            return False
        self._buckets[key].append(now)
        return True


_limiter = RateLimiter(max_requests=20, window=60)
_admin_limiter = RateLimiter(max_requests=10, window=60)


# ── Middleware ────────────────────────────────────────────────────────────────

async def security_middleware(request: Request, call_next):
    """Basic auth + rate limiting + security headers on every response."""
    # ── Basic auth gate ──
    if BASIC_AUTH_PASS:
        authorized = False
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                user, pwd = decoded.split(":", 1)
                authorized = (user == BASIC_AUTH_USER and pwd == BASIC_AUTH_PASS)
            except Exception:
                pass
        if not authorized:
            return Response(
                content="Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Wonder SOPs"'},
            )

    # ── Rate limiting ──
    client_ip = (request.client.host if request.client else "unknown")
    if request.url.path.startswith("/api/"):
        limiter = _admin_limiter if request.url.path.startswith("/api/admin/") else _limiter
        if not limiter.is_allowed(client_ip):
            return JSONResponse({"error": "Rate limit exceeded. Please slow down."}, status_code=429)

    response = await call_next(request)

    # ── Security headers ──
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    return response
