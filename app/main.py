import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import Base, engine
from app.routers import protocols, upload
from app.storage import ensure_bucket_exists, get_minio_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Secretary", version="1.0.0")
templates = Jinja2Templates(directory="templates")

app.include_router(upload.router)
app.include_router(protocols.router)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    logger.info("Ensuring MinIO bucket exists...")
    minio = get_minio_client()
    ensure_bucket_exists(minio)

    logger.info("AI Secretary ready")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})
