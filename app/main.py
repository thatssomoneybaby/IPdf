from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ensure_dirs
from routes import router
from worker import start_workers


ensure_dirs()

app = FastAPI(title="IPdf API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def _start_worker():
    start_workers()
