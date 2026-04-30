"""FastAPI application entry point.

Wires the file/chat/health routers together and configures permissive CORS
so the static frontend (served on :8080) can talk to this API on :8000.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import chat, files, health

app = FastAPI(title="Claude RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(files.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {"service": "Claude RAG", "docs": "/docs"}
