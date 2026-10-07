import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Dish, KitchenOrder, OrderClosure, OrderLine, StockSnapshotLine
from app.services.order_gate import close_order, reopen_order

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

@router.post("/{order_id}/close")
def close(order_id: int, db: Session = Depends(get_db)):
    closure = close_order(db, order_id)
    return {"id": closure.id, "order_id": closure.order_id,
            "prep_run_id": closure.prep_run_id, "closed_at": closure.closed_at.isoformat(),
            "status": "closed"}

@router.post("/{order_id}/reopen")
def reopen(order_id: int, db: Session = Depends(get_db)):
    closure = reopen_order(db, order_id)
    return {"id": closure.id, "order_id": closure.order_id,
            "reopened_at": closure.reopened_at.isoformat(), "status": "open"}

@router.get("/{order_id}/closures")
def closures(order_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(OrderClosure).where(OrderClosure.order_id == order_id).order_by(OrderClosure.id)
    ).all()
    out = []
    for c in rows:
        snaps = db.scalars(
            select(StockSnapshotLine).where(StockSnapshotLine.closure_id == c.id)
            .order_by(StockSnapshotLine.id)
        ).all()
        out.append({
            "id": c.id,
            "closed_at": c.closed_at.isoformat() if c.closed_at else None,
            "reopened_at": c.reopened_at.isoformat() if c.reopened_at else None,
            "prep_run_id": c.prep_run_id,
            "prep": json.loads(c.prep_snapshot_json),
            "stock_snapshot": [
                {"ingredient_id": s.ingredient_id, "code": s.code, "name": s.name,
                 "unit": s.unit, "stock_qty": s.stock_qty}
                for s in snaps
            ],
        })
    return out
