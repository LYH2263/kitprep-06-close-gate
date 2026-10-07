import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Dish, KitchenOrder, OrderLine, PrepSnapshot
from app.services.gate import ORDER_CLOSED, ORDER_OPEN, is_closed
from app.services.prep_service import compute_prep_result

router = APIRouter(prefix="/orders", tags=["orders"])

@router.get("")
def list_orders(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "outlet": r.outlet, "status": r.status}
            for r in db.scalars(select(KitchenOrder).order_by(KitchenOrder.id)).all()]

@router.get("/{order_id}/lines")
def order_lines(order_id: int, db: Session = Depends(get_db)):
    dishes = {d.id: d for d in db.scalars(select(Dish)).all()}
    rows = db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    return [{"id": r.id, "dish_id": r.dish_id, "dish_name": dishes[r.dish_id].name, "portions": r.portions}
            for r in rows]

@router.get("/{order_id}/snapshots")
def order_snapshots(order_id: int, db: Session = Depends(get_db)):
    order = db.get(KitchenOrder, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    rows = db.scalars(select(PrepSnapshot).where(PrepSnapshot.order_id == order_id)
                      .order_by(PrepSnapshot.id.desc())).all()
    return [{"id": s.id, "order_id": s.order_id, "closed_at": s.closed_at.isoformat(),
             "result": json.loads(s.result_json)} for s in rows]

@router.post("/{order_id}/close")
def close_order(order_id: int, db: Session = Depends(get_db)):
    """截单收档：落下闸门 + 截住那一刻的备料快照，同一事务落库；失败整体回退。"""
    order = db.get(KitchenOrder, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    if is_closed(order):
        raise HTTPException(409, "订单已截档")
    try:
        result = compute_prep_result(db, order_id)
        if not result["prep_lines"]:
            raise HTTPException(400, "没有任何备料结果的空订单禁止截档")
        result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
        closed_at = datetime.utcnow()
        result["closed_at"] = closed_at.isoformat()
        db.add(PrepSnapshot(order_id=order.id, closed_at=closed_at,
                            result_json=json.dumps(result, ensure_ascii=False)))
        order.status = ORDER_CLOSED
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, "截档失败")
    return {"id": order.id, "code": order.code, "status": order.status, "closed_at": closed_at.isoformat()}

@router.post("/{order_id}/reopen")
def reopen_order(order_id: int, db: Session = Depends(get_db)):
    """重新打开：只抬闸门，已落下的截档快照保持原字不动。"""
    order = db.get(KitchenOrder, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    if not is_closed(order):
        raise HTTPException(409, "订单未截档")
    order.status = ORDER_OPEN
    db.commit()
    return {"id": order.id, "code": order.code, "status": order.status}
