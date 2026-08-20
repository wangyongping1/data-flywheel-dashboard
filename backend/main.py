from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.flywheel import router as flywheel_router
from routers.annotation import router as annotation_router
from routers.imports import router as imports_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 自动调度 Langfuse 增量同步（LANGFUSE_SYNC_ENABLED=1 开启，默认关闭）
    if os.getenv("LANGFUSE_SYNC_ENABLED", "0") == "1":
        from services.langfuse_sync import langfuse_sync

        interval = int(os.getenv("LANGFUSE_SYNC_INTERVAL_SECONDS", "300"))
        langfuse_sync.start_scheduler(interval_seconds=interval)
    yield


app = FastAPI(title="数据飞轮 Dashboard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(flywheel_router)
app.include_router(annotation_router)
app.include_router(imports_router)


@app.get("/")
def root():
    return {"service": "数据飞轮 Dashboard API", "docs": "/docs"}
