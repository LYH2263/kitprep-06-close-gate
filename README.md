# KitPrep 中央厨房 BOM 备料

按菜品 BOM 展开订单行、合并同原料需求，对照库存计算缺料并生成备料单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:5000 |
| API | http://localhost:10100 |
| API 文档 | http://localhost:10100/docs |
| Postgres | localhost:5451 |

健康检查：`GET http://localhost:10100/api/health`

## 使用说明

1. 在「菜品」「BOM」维护中央厨房出品与用料树。
2. 在「订单」「库存」确认当日需求与现有库存。
3. 打开「备料单」展开合并原料需求。
4. 在「缺料」查看 need − stock 为正的原料。
5. 在「订单」点「截单收档」：落下闸门并把那一刻的备料快照单独落库钉死；截住后「生成备料单」关闭（再点返回 `已截单不能再生成`），缺料贴只读快照。「重新打开」后才可按当时定额与结存生成新单，已截快照保持原字。
6. 在「库存」可「加账面」改结存（只加不减），只动库存表，不带动已截订单与缺料贴。

## 开发与测试

```bash
docker compose exec api pytest -q
```
