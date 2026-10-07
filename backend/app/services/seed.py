from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import BomLine, Dish, Ingredient, KitchenOrder, OrderLine, PrepRun
from app.services.order_gate import STATUS_OPEN
from app.services.prep_service import generate_prep

def seed_if_empty(db: Session) -> None:
    if (db.scalar(select(func.count()).select_from(Dish)) or 0) > 0:
        return
    dishes = [("D-HS", "红烧肉套餐"), ("D-YC", "鱼香茄子"), ("D-JT", "鸡汤面")]
    dish_ids = {}
    for code, name in dishes:
        d = Dish(code=code, name=name, portion_unit="份")
        db.add(d); db.flush(); dish_ids[code] = d.id
    ings = [
        ("I-PR", "五花肉", "kg", 8.0),
        ("I-EG", "茄子", "kg", 3.0),
        ("I-CK", "鸡肉", "kg", 5.0),
        ("I-RC", "大米", "kg", 20.0),
        ("I-ND", "面条", "kg", 4.0),
        ("I-SC", "生抽", "L", 2.0),
        ("I-OL", "食用油", "L", 1.5),
    ]
    ing_ids = {}
    for code, name, unit, stock in ings:
        i = Ingredient(code=code, name=name, unit=unit, stock_qty=stock)
        db.add(i); db.flush(); ing_ids[code] = i.id
    bom = [
        ("D-HS", "I-PR", 0.25), ("D-HS", "I-RC", 0.15), ("D-HS", "I-SC", 0.02), ("D-HS", "I-OL", 0.03),
        ("D-YC", "I-EG", 0.3), ("D-YC", "I-RC", 0.15), ("D-YC", "I-SC", 0.015), ("D-YC", "I-OL", 0.025),
        ("D-JT", "I-CK", 0.12), ("D-JT", "I-ND", 0.2), ("D-JT", "I-SC", 0.01),
    ]
    for dcode, icode, qty in bom:
        db.add(BomLine(dish_id=dish_ids[dcode], ingredient_id=ing_ids[icode], qty_per_portion=qty))
    order = KitchenOrder(code="KO-0901", outlet="城西门店", status="open")
    db.add(order); db.flush()
    for dcode, portions in [("D-HS", 40), ("D-YC", 30), ("D-JT", 50)]:
        db.add(OrderLine(order_id=order.id, dish_id=dish_ids[dcode], portions=portions))
    db.flush()
    # 让演示订单开箱即有一张备料单（可直接体验截档）。
    generate_prep(db, order.id)
    db.commit()


def ensure_demo_prep_run(db: Session) -> None:
    """老数据卷不会触发 seed_if_empty：给尚无备料单的营业演示订单补一张，幂等。"""
    order = db.scalars(
        select(KitchenOrder).where(KitchenOrder.code == "KO-0901")
    ).first() or db.scalars(select(KitchenOrder).order_by(KitchenOrder.id)).first()
    if order is None or order.status != STATUS_OPEN:
        return
    exists = db.scalar(select(func.count()).select_from(PrepRun).where(PrepRun.order_id == order.id)) or 0
    if exists > 0:
        return
    generate_prep(db, order.id)
