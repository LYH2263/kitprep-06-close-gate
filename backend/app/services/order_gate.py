"""订单关闸的唯一口径（订单页截档与备料台生成共用本模块）。

锁序约定（结构性杜绝死锁）：
- 生成 / 截档 / 重开：只锁 kitchen_orders 行（FOR UPDATE）；
- 库存只加账面：只锁 ingredients 行，永不锁订单行。
两套锁集合互不相交，因此「截档中加库存 + 再点生成」无论怎样交错：
生成必失败（已截单不能再生成），库存账面照常加上。
"""
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Ingredient, KitchenOrder, OrderClosure, PrepRun, StockSnapshotLine

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

MSG_CLOSED_GENERATE = "已截单不能再生成"
MSG_EMPTY = "无备料结果的空订单不能截档"
MSG_ALREADY_CLOSED = "订单已截档，请勿重复操作"
MSG_NOT_CLOSED = "订单未截档，不能重新打开"
MSG_ORDER_MISSING = "订单不存在"
MSG_PREP_MISSING = "备料单不存在"


class GateError(Exception):
    """业务闸门错误；响应体由 main.py 的处理器原样输出为纯文本。"""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def lock_order(db: Session, order_id: int) -> KitchenOrder:
    """先锁行，再由调用方判断状态。订单不存在 -> 404。"""
    order = db.scalars(
        select(KitchenOrder).where(KitchenOrder.id == order_id).with_for_update()
    ).first()
    if not order:
        raise GateError(MSG_ORDER_MISSING, 404)
    return order


def get_active_closure(db: Session, order_id: int) -> OrderClosure | None:
    """活动截档 = reopened_at IS NULL 的最新一条。"""
    return db.scalars(
        select(OrderClosure)
        .where(OrderClosure.order_id == order_id, OrderClosure.reopened_at.is_(None))
        .order_by(OrderClosure.id.desc())
    ).first()


def assert_open(db: Session, order_id: int) -> KitchenOrder:
    """生成备料单的闸门：锁行后确认仍在营业。状态位与截档行任一为截即拒。"""
    order = lock_order(db, order_id)
    if order.status == STATUS_CLOSED or get_active_closure(db, order_id) is not None:
        raise GateError(MSG_CLOSED_GENERATE)
    return order


def close_order(db: Session, order_id: int) -> OrderClosure:
    """截单收档：闸门、备料快照、活结存三套数据同一事务落库；不做出库扣减。"""
    order = lock_order(db, order_id)
    if order.status == STATUS_CLOSED or get_active_closure(db, order_id) is not None:
        raise GateError(MSG_ALREADY_CLOSED)

    # 锁行之后才查「最新一张备料单」，钉死截住那一刻的结果。
    run = db.scalars(
        select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
    ).first()
    run_data = json.loads(run.result_json) if run else {}
    if not run or not run_data.get("prep_lines"):
        # 空订单禁截——在任何写入之前拒绝。
        raise GateError(MSG_EMPTY)

    try:
        closure = OrderClosure(
            order_id=order.id,
            prep_run_id=run.id,
            prep_snapshot_json=run.result_json,
        )
        db.add(closure)
        db.flush()  # 取得 closure.id 供快照行挂接

        ingredients = db.scalars(select(Ingredient).order_by(Ingredient.id)).all()
        db.add_all([
            StockSnapshotLine(
                closure_id=closure.id,
                ingredient_id=ing.id,
                code=ing.code,
                name=ing.name,
                unit=ing.unit,
                stock_qty=ing.stock_qty,
            )
            for ing in ingredients
        ])

        order.status = STATUS_CLOSED
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(closure)
    return closure


def reopen_order(db: Session, order_id: int) -> OrderClosure:
    """重新打开：翻转闸门并合上历史截档行；所钉备料单与快照一律不动。"""
    order = lock_order(db, order_id)
    closure = get_active_closure(db, order_id)
    if order.status != STATUS_CLOSED or closure is None:
        raise GateError(MSG_NOT_CLOSED)
    try:
        closure.reopened_at = datetime.utcnow()
        order.status = STATUS_OPEN
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(closure)
    return closure
