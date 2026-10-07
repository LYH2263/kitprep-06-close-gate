from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.prep_service import generate_prep, latest_prep
router = APIRouter(prefix="/prep", tags=["prep"])

@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    return generate_prep(db, order_id)

@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    return latest_prep(db, order_id)

@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    data = latest_prep(db, order_id)
    return {"order_id": order_id, "shortages": data.get("shortages", []), "stats": data.get("stats", {})}
