from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.order_gate import GateError
from app.services.seed import ensure_demo_prep_run, seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
            ensure_demo_prep_run(db)
        finally:
            db.close()
    yield


app = FastAPI(title="KitPrep", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(GateError)
async def gate_error_handler(_request: Request, exc: GateError):
    # 失败句逐字返回（如「已截单不能再生成」），不带 JSON 包装。
    return PlainTextResponse(exc.message, status_code=exc.status_code,
                             media_type="text/plain; charset=utf-8")

app.include_router(api_router, prefix="/api")
