import math

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Ingredient
from app.services.order_gate import GateError

router = APIRouter(prefix="/inventory", tags=["inventory"])

class AdjustBody(BaseModel):
    add_qty: float

@router.get("")
def list_inventory(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "name": r.name, "unit": r.unit, "stock_qty": r.stock_qty}
            for r in db.scalars(select(Ingredient).order_by(Ingredient.id)).all()]

@router.post("/{ingredient_id}/adjust")
def adjust_stock(ingredient_id: int, body: AdjustBody, db: Session = Depends(get_db)):
    """库存只加账面：唯一的写入口，只锁原料行，不触碰订单/备料/缺料，不做出库扣减。"""
    if not math.isfinite(body.add_qty) or body.add_qty <= 0:
        raise GateError("库存增加量必须大于0", 400)
    ing = db.scalars(
        select(Ingredient).where(Ingredient.id == ingredient_id).with_for_update()
    ).first()
    if not ing:
        raise GateError("原料不存在", 404)
    ing.stock_qty = (ing.stock_qty or 0.0) + body.add_qty
    db.commit()
    db.refresh(ing)
    return {"id": ing.id, "stock_qty": ing.stock_qty}
