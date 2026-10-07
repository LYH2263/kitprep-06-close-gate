"""订单截单闸门：订单页截档与备料台生成共用同一套关闸口径。"""
from __future__ import annotations

from app.models.models import KitchenOrder

ORDER_OPEN = "open"
ORDER_CLOSED = "closed"

MSG_CLOSED_NO_GENERATE = "已截单不能再生成"


def is_closed(order: KitchenOrder) -> bool:
    """唯一关闸口径：status == closed 即闸门落下。"""
    return order.status == ORDER_CLOSED
