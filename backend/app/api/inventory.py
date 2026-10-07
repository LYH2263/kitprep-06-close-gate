from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Ingredient
router = APIRouter(prefix="/inventory", tags=["inventory"])

@router.get("")
def list_inventory(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "name": r.name, "unit": r.unit, "stock_qty": r.stock_qty}
            for r in db.scalars(select(Ingredient).order_by(Ingredient.id)).all()]

class AdjustIn(BaseModel):
    ingredient_id: int
    qty: float

@router.post("/adjust")
def adjust_stock(body: AdjustIn, db: Session = Depends(get_db)):
    """改结存：只加账面、只动库存表；不带动任何已截订单与缺料贴，不做领料出库。"""
    ing = db.get(Ingredient, body.ingredient_id)
    if not ing: raise HTTPException(404, "原料不存在")
    if body.qty <= 0: raise HTTPException(400, "只许加账面，数量必须为正")
    ing.stock_qty = round(ing.stock_qty + body.qty, 3)
    db.commit(); db.refresh(ing)
    return {"id": ing.id, "code": ing.code, "name": ing.name, "unit": ing.unit, "stock_qty": ing.stock_qty}
