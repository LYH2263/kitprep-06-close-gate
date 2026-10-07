"""备料计算：按当前 BOM 定额与活结存展开订单，供生成备料单与截档快照共用。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import BomLine, Ingredient, OrderLine
from app.services.bom_engine import explode_and_merge, result_to_dict


def compute_prep_result(db: Session, order_id: int) -> dict:
    """按调用这一刻的 BOM 定额与活结存现算备料结果（不落库）。"""
    ols = [{"dish_id": l.dish_id, "portions": l.portions}
           for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()]
    bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
           for b in db.scalars(select(BomLine)).all()]
    ings = {i.id: {"code": i.code, "name": i.name, "unit": i.unit, "stock_qty": i.stock_qty}
            for i in db.scalars(select(Ingredient)).all()}
    return result_to_dict(explode_and_merge(ols, bom, ings))
