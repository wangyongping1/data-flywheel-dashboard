from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.flywheel import router as flywheel_router
from routers.annotation import router as annotation_router

app = FastAPI(title="数据飞轮 Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(flywheel_router)
app.include_router(annotation_router)


@app.get("/")
def root():
    return {"service": "数据飞轮 Dashboard API", "docs": "/docs"}
