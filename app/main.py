import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Base, engine
from .routers import asha, auth, authority, calls, consult, patient, pharmacy, scan

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # For production use Alembic migrations instead of create_all
    Base.metadata.create_all(engine)
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


app = FastAPI(title="RuralCare API", version="1.0.0", lifespan=lifespan,
              description="Telemedicine and medicine tracking for rural patients")

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, pharmacy.router, scan.router, patient.router, consult.router,
          asha.router, authority.router, calls.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "demo": settings.demo_mode}


# The web app is served from the same origin as the API (must be mounted last)
if os.path.isdir(settings.frontend_dir):
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
