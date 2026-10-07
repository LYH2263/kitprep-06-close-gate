import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import KitchenOrder, PrepRun, PrepSnapshot
from app.services.gate import MSG_CLOSED_NO_GENERATE, is_closed
from app.services.prep_service import compute_prep_result
router = APIRouter(prefix="/prep", tags=["prep"])

@router.post("/run")
def run_prep(order_id: int = 1, db: Session = Depends(get_db)):
    order = db.get(KitchenOrder, order_id)
    if not order: raise HTTPException(404, "订单不存在")
    if is_closed(order): raise HTTPException(409, MSG_CLOSED_NO_GENERATE)
    result = compute_prep_result(db, order_id)
    result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
    run = PrepRun(order_id=order_id, created_at=datetime.utcnow(), result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, "closed": False, **result}

@router.get("/latest")
def latest(order_id: int = 1, db: Session = Depends(get_db)):
    order = db.get(KitchenOrder, order_id)
    if not order: raise HTTPException(404, "订单不存在")
    if is_closed(order):
        # 已截单：只读截住那一刻落下的快照，禁止按活结存现算
        snap = db.scalars(select(PrepSnapshot).where(PrepSnapshot.order_id == order_id)
                          .order_by(PrepSnapshot.id.desc())).first()
        if not snap: raise HTTPException(404, "无截档快照")
        return {"id": snap.id, "closed": True, **json.loads(snap.result_json)}
    run = db.scalars(select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())).first()
    if not run:
        return run_prep(order_id=order_id, db=db)
    data = json.loads(run.result_json)
    return {"id": run.id, "closed": False, **data}

@router.get("/shortages")
def shortages(order_id: int = 1, db: Session = Depends(get_db)):
    data = latest(order_id=order_id, db=db)
    return {"order_id": order_id, "closed": data.get("closed", False),
            "shortages": data.get("shortages", []), "stats": data.get("stats", {})}
