# 独角鲸云来源

`dujiaojing` 来源用于监控 `api.fuckip.me` 的套餐接口，需要 token。

## 配置

```json
{
  "enabled": true,
  "api_url": "https://api.fuckip.me/api/v1/plans",
  "token_env": "SITE_A_TOKEN",
  "deploy_url": "https://dash.fuckip.me/deploy?plan_id={plan_id}&machine_id={machine_id}&region={region}",
  "page_size": 200,
  "max_pages": 50
}
```

## 环境变量

```bash
SITE_A_TOKEN=replace-with-your-token
```

不要把 token 写进 JSON 或 README。

## 字段映射

| 原始字段 | Offer 字段 | 说明 |
|---|---|---|
| `id` | `external_id` | plan id |
| `name` | `name` | 套餐名 |
| `machine_name` | `provider/region` | 节点名 |
| `machine_region` | `region` | 地区 |
| `machine_id` | 购买链接参数 | deploy URL 需要 |
| `cpu` | `cpu_cores` | 数值 |
| `ram_mb` | `ram_gb` | MB 转 GB |
| `disk_gb` | `disk` | 磁盘 |
| `bandwidth_mbps` | `bandwidth` | 带宽 |
| `monthly_traffic_gb` | `traffic` | 月流量 |
| `price_monthly` | `price.usd_month` | 月价 |
| `remaining` | `stock` | 库存数量 |

## 推荐规则

| 规则 | 推荐值 | 说明 |
|---|---:|---|
| `price_max_usd_month` | `0.3` | 控制极低价池 |
| `limit_events` | `12` | 避免一次推太多 |
| `sort_events` | `pool_price` | 命中池优先 |

## 常见池

```json
{
  "name": "超低价",
  "ram_min_gb": 0,
  "ram_max_gb": 1024,
  "usd_year_min": 0,
  "usd_year_max": 0.96
}
```

```json
{
  "name": "优化线路",
  "ram_min_gb": 0,
  "ram_max_gb": 1024,
  "usd_year_min": 0,
  "usd_year_max": 3.6
}
```

## dry-run

```bash
set -a
. ./.env
set +a
vpsmon-v4 --config config.local.json --source dujiaojing --notify-first-run --dry-run
```

## 排错

| 现象 | 处理 |
|---|---|
| token 报错 | 确认 `SITE_A_TOKEN` 已加载到当前 shell 或 systemd 环境 |
| 购买链接参数缺失 | 检查原始响应是否还有 `machine_id` / `machine_region` |
| route 很脏 | 在 source normalize 做来源级清理，通用截断放 formatter |
| 首轮刷屏 | 先 dry-run 或 summary，不要直接 `--notify-first-run --send` |
