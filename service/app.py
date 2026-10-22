from __future__ import annotations

import os
import secrets
import sqlite3
import string
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

DB_PATH = Path(os.getenv("URL_SHORTENER_DB", "url_shortener.db"))
ALPHABET = string.ascii_letters + string.digits

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_db()
    yield


app = FastAPI(title="URL Shortener API", version="0.1.0", description="Assessment prototype: short URLs and click analytics", lifespan=lifespan)


class CreateURLRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048, description="Absolute HTTP or HTTPS URL")

    @field_validator("url")
    @classmethod
    def valid_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
            raise ValueError("url must be an absolute http or https URL")
        if any(ch.isspace() for ch in value):
            raise ValueError("url must not contain whitespace")
        return value


class URLResponse(BaseModel):
    code: str
    short_url: str
    original_url: str
    created_at: str


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_db() -> None:
    with connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS urls (
            code TEXT PRIMARY KEY,
            original_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL REFERENCES urls(code),
            clicked_at TEXT NOT NULL,
            user_agent TEXT
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clicks_code_clicked_at ON clicks(code, clicked_at)")


def make_code(length: int = 7) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


@app.get("/healthz", tags=["operations"])
def healthz():
    return {"status": "ok"}


@app.post("/api/urls", response_model=URLResponse, status_code=status.HTTP_201_CREATED, tags=["urls"])
def create_url(payload: CreateURLRequest, request: Request):
    created_at = datetime.now(timezone.utc).isoformat()
    for _ in range(5):
        code = make_code()
        try:
            with connection() as conn:
                conn.execute("INSERT INTO urls(code, original_url, created_at) VALUES (?, ?, ?)",
                             (code, payload.url, created_at))
            base = str(request.base_url).rstrip("/")
            return URLResponse(code=code, short_url=f"{base}/{code}", original_url=payload.url, created_at=created_at)
        except sqlite3.IntegrityError:
            continue
    raise HTTPException(status_code=503, detail="Could not allocate a unique short code; retry the request")


@app.get("/api/urls/{code}/analytics", tags=["analytics"])
def analytics(code: str):
    with connection() as conn:
        row = conn.execute("SELECT code, original_url, created_at FROM urls WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Short code not found")
        clicks = conn.execute("SELECT COUNT(*) AS total FROM clicks WHERE code = ?", (code,)).fetchone()["total"]
        latest = conn.execute("SELECT clicked_at FROM clicks WHERE code = ? ORDER BY id DESC LIMIT 1", (code,)).fetchone()
    return {"code": row["code"], "original_url": row["original_url"], "created_at": row["created_at"],
            "click_count": clicks, "last_clicked_at": latest["clicked_at"] if latest else None}


@app.get(
    "/{code}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=Response,
    responses={404: {"description": "Short code not found"}},
    tags=["redirects"],
)
def redirect(code: str, request: Request):
    with connection() as conn:
        row = conn.execute("SELECT original_url FROM urls WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Short code not found")
        conn.execute("INSERT INTO clicks(code, clicked_at, user_agent) VALUES (?, ?, ?)",
                     (code, datetime.now(timezone.utc).isoformat(), request.headers.get("user-agent", "")[:512]))
        original_url = row["original_url"]
    return Response(status_code=307, headers={"Location": original_url, "Cache-Control": "no-store"})
