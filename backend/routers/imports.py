from fastapi import APIRouter, HTTPException

from services.langfuse_sync import langfuse_sync

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/langfuse")
def trigger_langfuse_sync(body: dict = None):
    body = body or {}
    force_full = bool(body.get("force_full", False))
    job_id = langfuse_sync.start_sync_job(force_full=force_full)
    return {
        "status": "started",
        "job_id": job_id,
        "message": "Langfuse sync started",
    }


@router.get("/jobs")
def list_jobs():
    return {"jobs": langfuse_sync.get_all_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = langfuse_sync.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job