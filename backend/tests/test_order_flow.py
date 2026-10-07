import json
import os
import threading

import pytest
from sqlalchemy import create_engine, func, select

from app.main import app
from app.models.models import (
    BomLine, Dish, Ingredient, KitchenOrder, OrderClosure, OrderLine, PrepRun, StockSnapshotLine,
)
from app.services import order_gate
from app.services.order_gate import GateError


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _close(client, oid):
    return client.post(f"/api/orders/{oid}/close")


# 1. 营业中生成 -> 恰好一张新备料单
def test_generate_open_creates_one_run(client, db, make_order):
    o = make_order(with_run=False)
    r = client.post(f"/api/prep/run?order_id={o['order_id']}")
    assert r.status_code == 200
    assert _count(db, PrepRun) == 1
    body = r.json()
    assert body["prep_lines"] and body["shortages"] == [] and "stats" in body


# 2. 没有任何备料结果 -> 禁止截档
def test_close_without_run_rejected(client, db, make_order):
    o = make_order(with_run=False)
    r = _close(client, o["order_id"])
    assert r.status_code == 409
    assert r.text == "无备料结果的空订单不能截档"
    db.expire_all()
    assert db.get(KitchenOrder, o["order_id"]).status == "open"
    assert _count(db, OrderClosure) == 0
    assert _count(db, StockSnapshotLine) == 0


# 3. 空 prep_lines 的备料单也算空订单
def test_close_with_empty_prep_lines_rejected(client, db, make_order):
    o = make_order(empty_run=True)
    r = _close(client, o["order_id"])
    assert r.status_code == 409
    assert r.text == "无备料结果的空订单不能截档"
    db.expire_all()
    assert db.get(KitchenOrder, o["order_id"]).status == "open"
    assert _count(db, OrderClosure) == 0
    # 旧的缺料数据原样可读
    sh = client.get(f"/api/prep/shortages?order_id={o['order_id']}").json()
    assert sh["shortages"] == []


# 4. 截档写入中途失败 -> 状态/截档行/快照全数回滚
def test_close_failure_rolls_back(db, make_order, monkeypatch):
    from fastapi.testclient import TestClient
    o = make_order()
    stock_before = db.scalar(select(func.sum(Ingredient.stock_qty)))

    # closure flush 之后、构造快照行时炸掉
    class BoomLine(order_gate.StockSnapshotLine):
        def __init__(self, *args, **kwargs):
            raise RuntimeError("snapshot write failed")

    monkeypatch.setattr(order_gate, "StockSnapshotLine", BoomLine)
    r = TestClient(app, raise_server_exceptions=False).post(f"/api/orders/{o['order_id']}/close")
    assert r.status_code == 500
    monkeypatch.undo()

    db.expire_all()
    assert db.get(KitchenOrder, o["order_id"]).status == "open"
    assert _count(db, OrderClosure) == 0
    assert _count(db, StockSnapshotLine) == 0
    stock_after = db.scalar(select(func.sum(Ingredient.stock_qty)))
    assert stock_before == stock_after


# 5. 截档成功：闸门/备料快照/活结存三套落库，且无出库扣减
def test_close_persists_three_record_sets(client, db, make_order):
    o = make_order()
    run = db.scalars(select(PrepRun).where(PrepRun.order_id == o["order_id"])).one()
    stock_before = db.scalar(select(func.sum(Ingredient.stock_qty)))
    ing_count = _count(db, Ingredient)

    r = _close(client, o["order_id"])
    assert r.status_code == 200
    assert r.json()["status"] == "closed"

    db.expire_all()
    order = db.get(KitchenOrder, o["order_id"])
    assert order.status == "closed"
    closure = db.scalars(select(OrderClosure)).one()
    assert closure.order_id == order.id
    assert closure.prep_run_id == run.id
    # 截住那一刻的备料单原样复制
    assert closure.prep_snapshot_json == run.result_json
    # 活结存独立成套，全部原料各一行
    snaps = db.scalars(select(StockSnapshotLine)).all()
    assert len(snaps) == ing_count
    assert {s.ingredient_id for s in snaps} == {i.id for i in db.scalars(select(Ingredient)).all()}
    # 截档不做出库：账面合计不变
    assert db.scalar(select(func.sum(Ingredient.stock_qty))) == stock_before


# 6. 已截再生成 -> 409 纯文本逐字句，且不落新单
def test_generate_on_closed_exact_sentence(client, db, make_order):
    o = make_order()
    assert _close(client, o["order_id"]).status_code == 200

    r = client.post(f"/api/prep/run?order_id={o['order_id']}")
    assert r.status_code == 409
    assert r.content.decode() == "已截单不能再生成"
    assert r.headers["content-type"].startswith("text/plain")
    assert _count(db, PrepRun) == 1


# 7. 截后加库存：活账面变，冻结单据与缺料贴不动
def test_closed_latest_and_shortages_pinned_against_live_adjust(client, db, make_order):
    o = make_order(stock=0.2)  # need=1.0, shortage=0.8
    run_before = db.scalars(select(PrepRun).where(PrepRun.order_id == o["order_id"])).one().result_json
    closed = _close(client, o["order_id"])
    assert closed.status_code == 200
    pinned_run_id = closed.json()["prep_run_id"]

    r = client.post(f"/api/inventory/{o['ingredient_id']}/adjust", json={"add_qty": 100})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Ingredient, o["ingredient_id"]).stock_qty == pytest.approx(100.2)

    latest = client.get(f"/api/prep/latest?order_id={o['order_id']}").json()
    assert latest["id"] == pinned_run_id
    line = next(l for l in latest["prep_lines"] if l["ingredient_id"] == o["ingredient_id"])
    assert line["stock_qty"] == pytest.approx(0.2)
    assert line["shortage"] == pytest.approx(0.8)

    sh = client.get(f"/api/prep/shortages?order_id={o['order_id']}").json()
    stuck = next(x for x in sh["shortages"] if x["ingredient_id"] == o["ingredient_id"])
    assert stuck["shortage"] == pytest.approx(0.8)

    # 截档记录里的备料快照逐字不变
    cs = client.get(f"/api/orders/{o['order_id']}/closures").json()
    assert len(cs) == 1
    assert json.dumps(cs[0]["prep"], ensure_ascii=False, sort_keys=True) == \
           json.dumps(json.loads(run_before), ensure_ascii=False, sort_keys=True)
    assert cs[0]["stock_snapshot"][0]["stock_qty"] == pytest.approx(0.2)


# 8. 截档状态下加账面成功（可累计）
def test_adjust_succeeds_while_closed(client, db, make_order):
    o = make_order()
    assert _close(client, o["order_id"]).status_code == 200
    r = client.post(f"/api/inventory/{o['ingredient_id']}/adjust", json={"add_qty": 20})
    assert r.status_code == 200
    assert r.json()["stock_qty"] == pytest.approx(21.0)


# 9. 加库存校验：只许正数
def test_adjust_validation(client, db, make_order):
    o = make_order()
    for bad in (0, -1):
        r = client.post(f"/api/inventory/{o['ingredient_id']}/adjust", json={"add_qty": bad})
        assert r.status_code == 400
        assert r.text == "库存增加量必须大于0"
    r = client.post(
        f"/api/inventory/{o['ingredient_id']}/adjust",
        content=json.dumps({"add_qty": float("nan")}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.text == "库存增加量必须大于0"
    # 坏类型交给框架 422
    r = client.post(f"/api/inventory/{o['ingredient_id']}/adjust", json={"add_qty": "x"})
    assert r.status_code == 422
    db.expire_all()
    assert db.get(Ingredient, o["ingredient_id"]).stock_qty == pytest.approx(1.0)
    # 未知原料
    r = client.post("/api/inventory/9999/adjust", json={"add_qty": 1})
    assert r.status_code == 404
    assert r.text == "原料不存在"


# 10. 重开后按新定额/新结存出新单；旧钉单逐字不变
def test_reopen_then_regenerate_uses_current_bom_and_stock(client, db, make_order):
    o = make_order(stock=1.0)
    assert _close(client, o["order_id"]).status_code == 200
    old_closure_json = db.scalars(select(OrderClosure)).one().prep_snapshot_json
    old_run = db.scalars(select(PrepRun)).one()
    old_run_json = old_run.result_json

    r = client.post(f"/api/orders/{o['order_id']}/reopen")
    assert r.status_code == 200
    assert r.json()["status"] == "open"

    # 改定额 0.1 -> 0.2，账面 +10
    db.query(BomLine).filter_by(dish_id=o["dish_id"]).update({"qty_per_portion": 0.2})
    ing = db.get(Ingredient, o["ingredient_id"])
    ing.stock_qty += 10
    db.commit()

    r = client.post(f"/api/prep/run?order_id={o['order_id']}")
    assert r.status_code == 200
    body = r.json()
    line = next(l for l in body["prep_lines"] if l["ingredient_id"] == o["ingredient_id"])
    assert line["need_qty"] == pytest.approx(2.0)
    assert line["stock_qty"] == pytest.approx(11.0)
    assert line["shortage"] == 0

    db.expire_all()
    assert _count(db, PrepRun) == 2
    assert db.scalars(select(OrderClosure)).one().prep_snapshot_json == old_closure_json
    assert db.get(PrepRun, old_run.id).result_json == old_run_json


# 11. 截 -> 开 -> 再截：历史 append-only
def test_closure_history_append_only(client, db, make_order):
    o = make_order(code="KO-H")
    c1 = _close(client, o["order_id"]).json()
    assert client.post(f"/api/orders/{o['order_id']}/reopen").status_code == 200
    assert client.post(f"/api/prep/run?order_id={o['order_id']}").status_code == 200
    c2 = _close(client, o["order_id"]).json()

    rows = client.get(f"/api/orders/{o['order_id']}/closures").json()
    assert len(rows) == 2
    assert rows[0]["id"] == c1["id"]
    assert rows[0]["reopened_at"] is not None
    assert rows[0]["prep_run_id"] == c1["prep_run_id"]
    assert rows[1]["id"] == c2["id"]
    assert rows[1]["reopened_at"] is None
    assert rows[1]["prep_run_id"] != rows[0]["prep_run_id"]


# 12. 重复截档 / 重开营业单
def test_conflict_edges(client, make_order):
    o = make_order(code="KO-C")
    assert _close(client, o["order_id"]).status_code == 200
    r = _close(client, o["order_id"])
    assert r.status_code == 409
    assert r.text == "订单已截档，请勿重复操作"

    assert client.post(f"/api/orders/{o['order_id']}/reopen").status_code == 200
    r = client.post(f"/api/orders/{o['order_id']}/reopen")
    assert r.status_code == 409
    assert r.text == "订单未截档，不能重新打开"


# 13. 营业无单 GET latest 自动生成；截档后 GET 绝不生成且只回钉单
def test_latest_auto_then_pinned(client, db, make_order):
    o = make_order(code="KO-L", with_run=False)
    r = client.get(f"/api/prep/latest?order_id={o['order_id']}")
    assert r.status_code == 200
    assert _count(db, PrepRun) == 1
    pinned_id = r.json()["id"]

    assert _close(client, o["order_id"]).status_code == 200
    for _ in range(3):
        r = client.get(f"/api/prep/latest?order_id={o['order_id']}")
        assert r.status_code == 200
        assert r.json()["id"] == pinned_id
    assert _count(db, PrepRun) == 1


# 14. 不存在订单一律 404
def test_missing_order_404(client):
    for method, path in (
        ("post", "/api/prep/run?order_id=9999"),
        ("get", "/api/prep/latest?order_id=9999"),
        ("post", "/api/orders/9999/close"),
        ("post", "/api/orders/9999/reopen"),
    ):
        r = getattr(client, method)(path)
        assert r.status_code == 404
        assert r.text == "订单不存在"


# 15. Postgres 专属：截档态下「加库存 + 再点生成」并发
PG_URL = os.getenv("KP_TEST_PG_URL")


@pytest.mark.skipif(not PG_URL, reason="SQLite 无行锁；设 KP_TEST_PG_URL 指向 scratch 库才跑")
def test_pg_concurrent_closed_adjust_and_generate():
    from sqlalchemy.orm import sessionmaker as _sm

    eng = create_engine(PG_URL)
    Base = KitchenOrder.metadata
    Base.drop_all(eng)
    Base.create_all(eng)
    S = _sm(bind=eng, autoflush=False)
    try:
        s = S()
        dish = Dish(code="D-PG", name="并发菜")
        s.add(dish); s.flush()
        ing = Ingredient(code="I-PG", name="并发料", unit="kg", stock_qty=1.0)
        s.add(ing); s.flush()
        s.add(BomLine(dish_id=dish.id, ingredient_id=ing.id, qty_per_portion=0.1))
        order = KitchenOrder(code="KO-PG", outlet="并发店", status="open")
        s.add(order); s.flush()
        s.add(OrderLine(order_id=order.id, dish_id=dish.id, portions=10))
        oid, iid = order.id, ing.id
        from app.services.prep_service import generate_prep
        generate_prep(s, oid)  # 先有一张备料单，否则禁截
        order_gate.close_order(s, oid)  # 再截住
        s.close()

        errors, barrier = [], threading.Barrier(2)

        def gen():
            ss = S()
            try:
                barrier.wait()
                generate_prep(ss, oid)
                errors.append("generate should have failed")
            except GateError as e:
                if e.message != "已截单不能再生成":
                    errors.append(repr(e.message))
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
            finally:
                ss.close()

        def adjust():
            ss = S()
            try:
                barrier.wait()
                row = ss.scalars(
                    select(Ingredient).where(Ingredient.id == iid).with_for_update()
                ).one()
                row.stock_qty += 5
                ss.commit()
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
                ss.rollback()
            finally:
                ss.close()

        t1 = threading.Thread(target=gen)
        t2 = threading.Thread(target=adjust)
        t1.start(); t2.start(); t1.join(); t2.join()

        assert errors == []
        check = S()
        assert check.scalar(select(func.count()).select_from(PrepRun)) == 1
        assert check.get(Ingredient, iid).stock_qty == pytest.approx(6.0)
        check.close()
    finally:
        Base.drop_all(eng)
        eng.dispose()
