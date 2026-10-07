"""备料单生成与读取：写走关闸服务，读优先返回落钉的截档快照。"""
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import BomLine, Ingredient, KitchenOrder, OrderLine, PrepRun
from app.services.bom_engine import explode_and_merge, result_to_dict
from app.services.order_gate import GateError, MSG_PREP_MISSING, assert_open, get_active_closure


def _build_and_persist(db: Session, order: KitchenOrder) -> dict:
    ols = [{"dish_id": l.dish_id, "portions": l.portions}
           for l in db.scalars(select(OrderLine).where(OrderLine.order_id == order.id)).all()]
    bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id, "qty_per_portion": b.qty_per_portion}
           for b in db.scalars(select(BomLine)).all()]
    ings = {i.id: {"code": i.code, "name": i.name, "unit": i.unit, "stock_qty": i.stock_qty}
            for i in db.scalars(select(Ingredient)).all()}
    result = result_to_dict(explode_and_merge(ols, bom, ings))
    result["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
    run = PrepRun(order_id=order.id, created_at=datetime.utcnow(),
                  result_json=json.dumps(result, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, **result}


def generate_prep(db: Session, order_id: int) -> dict:
    """生成（含重新打开后的再生成）。已截订单在此被同一套闸门挡住。"""
    order = assert_open(db, order_id)
    return _build_and_persist(db, order)


def _run_to_dict(run: PrepRun) -> dict:
    return {"id": run.id, **json.loads(run.result_json)}


def latest_prep(db: Session, order_id: int) -> dict:
    """读备料单：活动截档存在则只返回所钉那一份（绝不生成、绝不按活结存现算）；
    否则返回最新一次结果，营业中尚无结果时维持自动生成一份的旧行为。"""
    order = db.get(KitchenOrder, order_id)
    if not order:
        raise GateError("订单不存在", 404)

    closure = get_active_closure(db, order_id)
    if closure is not None:
        pinned = db.get(PrepRun, closure.prep_run_id)
        if pinned is None:
            raise GateError(MSG_PREP_MISSING, 404)
        return _run_to_dict(pinned)

    run = db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).first()
    if run is None:
        # 走同一道闸：万一在本请求期间订单被截住，这里同样失败，绝不落新单。
        return generate_prep(db, order_id)
    return _run_to_dict(run)
