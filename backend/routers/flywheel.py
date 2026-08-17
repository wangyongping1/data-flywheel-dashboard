from fastapi import APIRouter

from data.flywheel_aggregator import FlywheelAggregator

router = APIRouter(prefix="/api/flywheel", tags=["flywheel"])

aggregator = FlywheelAggregator()


@router.get("/summary")
def flywheel_summary():
    return aggregator.get_summary()


@router.get("/pipeline")
def flywheel_pipeline():
    return aggregator.get_pipeline()


@router.get("/events")
def flywheel_events():
    return aggregator.get_events()


@router.get("/evaluations")
def flywheel_evaluations():
    return aggregator.get_evaluations()


@router.get("/observations")
def flywheel_observations():
    return aggregator.get_observations()


@router.get("/training")
def flywheel_training():
    return aggregator.get_training_detail()
