import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    BomLine, Dish, Ingredient, KitchenOrder, OrderClosure, OrderLine,
    PrepRun, StockSnapshotLine,
)
from app.services.bom_engine import explode_and_merge, result_to_dict

# 纯内存 SQLite + 单连接；TestClient 不进 lifespan，避免触碰 Postgres。
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=engine)
TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_tables(db):
    """每个用例前清掉业务表，保证计数断言稳定。"""
    for model in (StockSnapshotLine, OrderClosure, PrepRun, OrderLine, BomLine,
                  KitchenOrder, Ingredient, Dish):
        db.query(model).delete()
    db.commit()
    yield


@pytest.fixture
def make_order(db):
    """造一条可配的订单：默认带菜品/原料/定额/订单行与一张有结果的备料单。"""
    def _make(code="KO-T", *, with_run=True, empty_run=False, with_lines=True,
              portions=10, stock=1.0):
        dish = Dish(code="D-" + code, name="测试菜" + code, portion_unit="份")
        db.add(dish); db.flush()
        ing = Ingredient(code="I-" + code, name="测试料" + code, unit="kg", stock_qty=stock)
        db.add(ing); db.flush()
        db.add(BomLine(dish_id=dish.id, ingredient_id=ing.id, qty_per_portion=0.1))
        order = KitchenOrder(code=code, outlet="测试门店", status="open")
        db.add(order); db.flush()
        if with_lines:
            db.add(OrderLine(order_id=order.id, dish_id=dish.id, portions=portions))
            db.flush()
        if with_run:
            if empty_run:
                payload = result_to_dict([])
            else:
                ols = [{"dish_id": l.dish_id, "portions": l.portions}
                       for l in db.query(OrderLine).filter_by(order_id=order.id).all()]
                bom = [{"dish_id": b.dish_id, "ingredient_id": b.ingredient_id,
                        "qty_per_portion": b.qty_per_portion}
                       for b in db.query(BomLine).all()]
                ings = {i.id: {"code": i.code, "name": i.name, "unit": i.unit,
                               "stock_qty": i.stock_qty} for i in db.query(Ingredient).all()}
                payload = result_to_dict(explode_and_merge(ols, bom, ings))
            payload["order"] = {"id": order.id, "code": order.code, "outlet": order.outlet}
            db.add(PrepRun(order_id=order.id,
                           result_json=json.dumps(payload, ensure_ascii=False)))
        db.commit()
        return {"order_id": order.id, "dish_id": dish.id, "ingredient_id": ing.id}
    return _make
