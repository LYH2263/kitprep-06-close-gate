"""截单收档 / 重新打开全生命周期：闸门、快照、活结存分套落库。"""
from app.database import SessionLocal
from app.models.models import KitchenOrder

ORDER_ID = 1  # 种子订单 KO-0901
PR_ID = 1     # 五花肉，种子库存 8.0，需求 10.0，缺 2.0


def _line(data, ingredient_id):
    return next(l for l in data["prep_lines"] if l["ingredient_id"] == ingredient_id)


def test_close_then_generate_fails_with_exact_message(client):
    r = client.post(f"/api/orders/{ORDER_ID}/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
    r = client.post(f"/api/prep/run?order_id={ORDER_ID}")
    assert r.status_code == 409
    assert r.json()["detail"] == "已截单不能再生成"
    # 订单页与备料台同一套关闸口径：状态已落下
    order = next(o for o in client.get("/api/orders").json() if o["id"] == ORDER_ID)
    assert order["status"] == "closed"


def test_close_freezes_snapshot_and_adjust_does_not_move_it(client):
    client.post(f"/api/orders/{ORDER_ID}/close")
    frozen = client.get(f"/api/prep/latest?order_id={ORDER_ID}").json()
    assert frozen["closed"] is True
    assert _line(frozen, PR_ID)["stock_qty"] == 8.0
    assert _line(frozen, PR_ID)["shortage"] == 2.0
    # 截住当中改结存：只加账面，成功
    r = client.post("/api/inventory/adjust", json={"ingredient_id": PR_ID, "qty": 100.0})
    assert r.status_code == 200
    assert r.json()["stock_qty"] == 108.0
    # 已截订单与缺料贴钉死原字，不随活结存动
    after = client.get(f"/api/prep/latest?order_id={ORDER_ID}").json()
    assert _line(after, PR_ID)["stock_qty"] == 8.0
    assert _line(after, PR_ID)["shortage"] == 2.0
    sticky = client.get(f"/api/prep/shortages?order_id={ORDER_ID}").json()
    assert sticky["closed"] is True
    assert next(s for s in sticky["shortages"] if s["ingredient_id"] == PR_ID)["shortage"] == 2.0
    # 活结存已是新账面
    inv = client.get("/api/inventory").json()
    assert next(i for i in inv if i["id"] == PR_ID)["stock_qty"] == 108.0


def test_generate_fails_and_adjust_succeeds_while_closed(client):
    client.post(f"/api/orders/{ORDER_ID}/close")
    # 截住当中：再点生成必须失败，加账面必须成功（两个方向各验一次）
    assert client.post(f"/api/prep/run?order_id={ORDER_ID}").status_code == 409
    assert client.post("/api/inventory/adjust", json={"ingredient_id": PR_ID, "qty": 1.0}).status_code == 200
    r = client.post(f"/api/prep/run?order_id={ORDER_ID}")
    assert r.status_code == 409
    assert r.json()["detail"] == "已截单不能再生成"
    assert client.post("/api/inventory/adjust", json={"ingredient_id": PR_ID, "qty": 1.0}).json()["stock_qty"] == 10.0


def test_reopen_then_generate_fresh_snapshot_keeps_original(client):
    client.post(f"/api/orders/{ORDER_ID}/close")
    client.post("/api/inventory/adjust", json={"ingredient_id": PR_ID, "qty": 100.0})
    r = client.post(f"/api/orders/{ORDER_ID}/reopen")
    assert r.status_code == 200
    assert r.json()["status"] == "open"
    # 重新打开后才许再点生成，按这一刻的定额与结存出新单
    r = client.post(f"/api/prep/run?order_id={ORDER_ID}")
    assert r.status_code == 200
    assert _line(r.json(), PR_ID)["stock_qty"] == 108.0
    assert _line(r.json(), PR_ID)["shortage"] == 0.0
    # 截住那一份保持原字
    snaps = client.get(f"/api/orders/{ORDER_ID}/snapshots").json()
    assert len(snaps) == 1
    assert _line(snaps[0]["result"], PR_ID)["stock_qty"] == 8.0
    assert _line(snaps[0]["result"], PR_ID)["shortage"] == 2.0
    # 再次截档落第二份快照，第一份仍不动
    client.post(f"/api/orders/{ORDER_ID}/close")
    snaps = client.get(f"/api/orders/{ORDER_ID}/snapshots").json()
    assert len(snaps) == 2
    assert _line(snaps[0]["result"], PR_ID)["stock_qty"] == 108.0
    assert _line(snaps[1]["result"], PR_ID)["stock_qty"] == 8.0


def test_close_empty_order_forbidden_and_rolls_back(client):
    db = SessionLocal()
    try:
        empty = KitchenOrder(code="KO-EMPTY", outlet="空门店", status="open")
        db.add(empty); db.commit(); db.refresh(empty)
        empty_id = empty.id
    finally:
        db.close()
    r = client.post(f"/api/orders/{empty_id}/close")
    assert r.status_code == 400
    # 截失败：订单状态、单条数、缺料贴都退回
    order = next(o for o in client.get("/api/orders").json() if o["id"] == empty_id)
    assert order["status"] == "open"
    assert client.get(f"/api/orders/{empty_id}/snapshots").json() == []
    sticky = client.get(f"/api/prep/shortages?order_id={empty_id}").json()
    assert sticky["shortages"] == []
    assert sticky["stats"]["ingredient_count"] == 0


def test_close_unknown_order_and_double_close_and_bad_reopen(client):
    assert client.post("/api/orders/9999/close").status_code == 404
    assert client.post(f"/api/orders/{ORDER_ID}/reopen").status_code == 409
    client.post(f"/api/orders/{ORDER_ID}/close")
    assert client.post(f"/api/orders/{ORDER_ID}/close").status_code == 409
    # 截档失败不留下任何痕迹
    order = next(o for o in client.get("/api/orders").json() if o["id"] == ORDER_ID)
    assert order["status"] == "closed"
    assert len(client.get(f"/api/orders/{ORDER_ID}/snapshots").json()) == 1


def test_adjust_only_adds_book(client):
    assert client.post("/api/inventory/adjust", json={"ingredient_id": PR_ID, "qty": 0}).status_code == 400
    assert client.post("/api/inventory/adjust", json={"ingredient_id": PR_ID, "qty": -5}).status_code == 400
    assert client.post("/api/inventory/adjust", json={"ingredient_id": 9999, "qty": 1}).status_code == 404
    inv = client.get("/api/inventory").json()
    assert next(i for i in inv if i["id"] == PR_ID)["stock_qty"] == 8.0
